import { useCallback, useEffect, useRef, useState } from "react";

import { pushLevel } from "./LiveWaveform";

// Browser microphone capture over WS /ws/meetings/{id}/audio (ADR 0004; browser fallback of
// ADR 0010). Frontend reconnection follows frontend-audio-reconnection.md: keep the
// microphone graph alive, queue a bounded number of frames and resume with the cursor.

export type CaptureState =
  | "idle"
  | "connecting"
  | "recording"
  | "reconnecting"
  | "disconnected"
  | "stopping"
  | "stopped"
  | "error";

const TARGET_RATE = 16_000;
const FRAME_SAMPLES = 4096; // 256 ms per frame
const MAX_QUEUED_FRAMES = 64;
const MAX_RECONNECT_ATTEMPTS = 6;
const LEVEL_SAMPLES = 1600; // one waveform level per 100 ms at 16 kHz

export interface CaptureStatus {
  state: CaptureState;
  level: number;
  /** Recent RMS levels for the live waveform, oldest first. */
  history: number[];
  seconds: number;
  error: string | null;
}

interface Resume {
  sessionId: string;
  nextSequence: number;
}

function socketUrl(meetingId: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/meetings/${meetingId}/audio`;
}

/** Downsample Float32 at `fromRate` to Int16 at 16 kHz by averaging each output interval. */
export function toPcm16(input: Float32Array, fromRate: number): Int16Array {
  const ratio = fromRate / TARGET_RATE;
  const length = Math.floor(input.length / ratio);
  const output = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.max(start + 1, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end && j < input.length; j++) sum += input[j];
    const sample = Math.max(-1, Math.min(1, sum / (end - start)));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

function rms(frame: Int16Array): number {
  let sum = 0;
  for (const sample of frame) sum += (sample / 0x8000) ** 2;
  return Math.sqrt(sum / Math.max(1, frame.length));
}

/** `onChanged` runs whenever the backend confirms a lifecycle change (ready, stopped). */
export function useMicrophoneCapture(meetingId: string, onChanged: () => void) {
  const [status, setStatus] = useState<CaptureStatus>({ state: "idle", level: 0, history: [], seconds: 0, error: null });
  const socket = useRef<WebSocket | null>(null);
  const audio = useRef<{ context: AudioContext; stream: MediaStream } | null>(null);
  const pending = useRef<Int16Array>(new Int16Array(0));
  const levelWindow = useRef<Int16Array>(new Int16Array(0));
  const queue = useRef<ArrayBuffer[]>([]);
  const resume = useRef<Resume | null>(null);
  const sent = useRef(0);
  const intentionalStop = useRef(false);
  const attempts = useRef(0);
  const changed = useRef(onChanged);
  changed.current = onChanged;

  const update = (patch: Partial<CaptureStatus>) => setStatus((current) => ({ ...current, ...patch }));

  const releaseAudio = useCallback(() => {
    audio.current?.stream.getTracks().forEach((track) => track.stop());
    void audio.current?.context.close();
    audio.current = null;
  }, []);

  const sendFrame = useCallback((frame: ArrayBuffer) => {
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN && resume.current) {
      ws.send(frame);
      sent.current += 1;
    } else {
      queue.current.push(frame);
      if (queue.current.length > MAX_QUEUED_FRAMES) queue.current.shift(); // bounded
    }
  }, []);

  const connect = useCallback(
    (command: Record<string, unknown>) => {
      const ws = new WebSocket(socketUrl(meetingId));
      ws.binaryType = "arraybuffer";
      socket.current = ws;
      ws.onopen = () => ws.send(JSON.stringify(command));
      ws.onmessage = (message) => {
        const event = JSON.parse(String(message.data));
        switch (event.type) {
          case "audio.ready":
            resume.current = { sessionId: event.session_id, nextSequence: event.next_sequence };
            sent.current = event.next_sequence;
            attempts.current = 0;
            update({ state: intentionalStop.current ? "stopping" : "recording", error: null });
            changed.current();
            if (intentionalStop.current) {
              ws.send(JSON.stringify({ type: "stop" }));
              break;
            }
            for (const frame of queue.current.splice(0)) sendFrame(frame);
            break;
          case "audio.received":
            update({ seconds: event.tracks?.microphone?.duration ?? 0 });
            break;
          case "audio.stopped":
            update({ seconds: event.tracks?.microphone?.duration ?? 0 });
            break;
          case "transcript.queued":
          case "transcript.failed":
            intentionalStop.current = true;
            resume.current = null;
            releaseAudio();
            update({ state: "stopped", level: 0, error: event.type === "transcript.failed" ? event.code : null });
            ws.close();
            changed.current();
            break;
          case "audio.error":
            if (
              [
                "STALE_CURSOR",
                "SESSION_NOT_RECOVERABLE",
                "MEETING_BUSY",
                "MEETING_NOT_FOUND",
                "MEETING_ALREADY_RECORDED",
                "AGENT_CAPTURE_ACTIVE",
                "SESSION_NOT_ACTIVE",
                "CAPTURE_LIMIT_REACHED",
              ].includes(event.code)
            ) {
              // The backend is not storing this audio: never keep showing "Grabando".
              intentionalStop.current = true;
              resume.current = null;
              releaseAudio();
              update({ state: "error", error: event.code, level: 0 });
              ws.close();
              changed.current();
            } else if (event.code === "INVALID_FRAME") {
              update({ error: event.code }); // one rejected frame: tell the user, keep recording
            }
            break;
        }
      };
      ws.onclose = () => {
        if (socket.current !== ws) return;
        if (!resume.current) {
          // Finished normally, or the socket closed before the session was ready.
          if (!intentionalStop.current) {
            releaseAudio();
            update({ state: "error", error: "NETWORK_ERROR", level: 0 });
          }
          return;
        }
        if (intentionalStop.current) {
          // The stop was not confirmed: the backend keeps the session recoverable.
          update({ state: "disconnected" });
          return;
        }
        // Unexpected loss: keep the microphone graph alive and try to resume.
        if (attempts.current >= MAX_RECONNECT_ATTEMPTS) {
          update({ state: "disconnected" });
          return;
        }
        attempts.current += 1;
        update({ state: "reconnecting" });
        const delay = Math.min(8000, 500 * 2 ** (attempts.current - 1));
        window.setTimeout(() => {
          if (!resume.current) return;
          connect({ type: "start", resume: true, session_id: resume.current.sessionId, next_sequence: sent.current });
        }, delay);
      };
    },
    [meetingId, releaseAudio, sendFrame],
  );

  const openMicrophone = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    const context = new AudioContext();
    await context.audioWorklet.addModule("/pcm-capture-worklet.js");
    const source = context.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(context, "pcm-capture");
    node.port.onmessage = (message: MessageEvent<Float32Array>) => {
      const samples = toPcm16(message.data, context.sampleRate);
      // Waveform levels every 100 ms, independent of the 256 ms transport frames.
      const window = new Int16Array(levelWindow.current.length + samples.length);
      window.set(levelWindow.current);
      window.set(samples, levelWindow.current.length);
      let levelOffset = 0;
      while (window.length - levelOffset >= LEVEL_SAMPLES) {
        const level = rms(window.subarray(levelOffset, levelOffset + LEVEL_SAMPLES));
        levelOffset += LEVEL_SAMPLES;
        setStatus((current) => ({ ...current, level, history: pushLevel(current.history, level) }));
      }
      levelWindow.current = window.slice(levelOffset);
      const merged = new Int16Array(pending.current.length + samples.length);
      merged.set(pending.current);
      merged.set(samples, pending.current.length);
      let offset = 0;
      while (merged.length - offset >= FRAME_SAMPLES) {
        const frame = merged.slice(offset, offset + FRAME_SAMPLES);
        offset += FRAME_SAMPLES;
        sendFrame(frame.buffer);
      }
      pending.current = merged.slice(offset);
    };
    source.connect(node);
    audio.current = { context, stream };
  }, [sendFrame]);

  const start = useCallback(
    async (recover?: Resume) => {
      intentionalStop.current = false;
      attempts.current = 0;
      queue.current = [];
      pending.current = new Int16Array(0);
      levelWindow.current = new Int16Array(0);
      update({ state: "connecting", error: null, level: 0, history: [] });
      try {
        await openMicrophone();
      } catch {
        update({ state: "error", error: "MICROPHONE_UNAVAILABLE" });
        return;
      }
      connect(
        recover
          ? { type: "start", resume: true, session_id: recover.sessionId, next_sequence: recover.nextSequence }
          : { type: "start" },
      );
    },
    [connect, openMicrophone],
  );

  const stop = useCallback(() => {
    intentionalStop.current = true;
    update({ state: "stopping" });
    releaseAudio();
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN && resume.current) {
      const flush = pending.current;
      if (flush.length) sendFrame(flush.slice().buffer);
      pending.current = new Int16Array(0);
      ws.send(JSON.stringify({ type: "stop" }));
    }
  }, [releaseAudio, sendFrame]);

  /** Finish a recoverable session left by a lost tab: resume without microphone, then stop. */
  const finalize = useCallback(
    (recover: Resume) => {
      intentionalStop.current = true;
      update({ state: "stopping", error: null });
      connect({ type: "start", resume: true, session_id: recover.sessionId, next_sequence: recover.nextSequence });
    },
    [connect],
  );

  useEffect(
    () => () => {
      intentionalStop.current = true;
      resume.current = null;
      socket.current?.close();
      releaseAudio();
    },
    [releaseAudio],
  );

  return { status, start, stop, finalize };
}
