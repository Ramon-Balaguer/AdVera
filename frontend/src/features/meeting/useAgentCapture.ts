import { useCallback, useEffect, useRef, useState } from "react";

import { pushLevel } from "./LiveWaveform";
import type { CaptureState } from "./useMicrophoneCapture";

// Native Capture Agent recording (ADR 0010): the backend owns PCM ingestion. The frontend
// opens the meeting audio session, asks the backend to start the agent's tracks, and then
// only receives lifecycle events, per-track metrics and RMS levels. It never carries PCM.

export type AgentTrack = "microphone" | "system";

export interface AgentCaptureStatus {
  state: CaptureState;
  seconds: number;
  levels: Partial<Record<AgentTrack, number>>;
  /** Recent RMS levels per track for the live waveforms, oldest first. */
  history: Partial<Record<AgentTrack, number[]>>;
  bytes: Partial<Record<AgentTrack, number>>;
  error: string | null;
}

const MAX_RECONNECT_ATTEMPTS = 6;

function wsUrl(path: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${path}`;
}

async function startAgentTracks(meetingId: string, tracks: AgentTrack[]) {
  const response = await fetch("/api/capture-agent/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meeting_id: meetingId, tracks }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "AGENT_UNAVAILABLE");
  return body as { capture_session_id: string; tracks: AgentTrack[] };
}

export function useAgentCapture(meetingId: string, onChanged: () => void) {
  const [status, setStatus] = useState<AgentCaptureStatus>({
    state: "idle",
    seconds: 0,
    levels: {},
    history: {},
    bytes: {},
    error: null,
  });
  const socket = useRef<WebSocket | null>(null);
  const levelSockets = useRef<WebSocket[]>([]);
  const session = useRef<string | null>(null);
  const intentionalStop = useRef(false);
  const attempts = useRef(0);
  const changed = useRef(onChanged);
  changed.current = onChanged;

  const update = (patch: Partial<AgentCaptureStatus>) => setStatus((current) => ({ ...current, ...patch }));

  const closeLevels = () => {
    levelSockets.current.forEach((ws) => ws.close());
    levelSockets.current = [];
  };

  const openLevels = (captureSessionId: string, tracks: AgentTrack[]) => {
    closeLevels();
    for (const track of tracks) {
      const ws = new WebSocket(wsUrl(`/ws/capture-agent/${captureSessionId}/${track}/levels`));
      ws.onmessage = (message) => {
        const event = JSON.parse(String(message.data));
        if (event.type === "levels") {
          setStatus((current) => ({
            ...current,
            levels: { ...current.levels, [track]: event.level },
            history: { ...current.history, [track]: pushLevel(current.history[track] ?? [], event.level) },
          }));
        }
      };
      levelSockets.current.push(ws);
    }
  };

  const connect = useCallback(
    (command: Record<string, unknown>, tracks: AgentTrack[]) => {
      const ws = new WebSocket(wsUrl(`/ws/meetings/${meetingId}/audio`));
      socket.current = ws;
      ws.onopen = () => ws.send(JSON.stringify(command));
      ws.onmessage = async (message) => {
        const event = JSON.parse(String(message.data));
        switch (event.type) {
          case "audio.ready": {
            session.current = event.session_id;
            attempts.current = 0;
            changed.current();
            if (event.resumed) {
              update({ state: intentionalStop.current ? "stopping" : "recording" });
              if (intentionalStop.current) ws.send(JSON.stringify({ type: "stop" }));
              break;
            }
            try {
              const capture = await startAgentTracks(meetingId, tracks);
              openLevels(capture.capture_session_id, capture.tracks);
              update({ state: "recording", error: null });
            } catch (error) {
              // The agent could not start: close the empty session without a job.
              intentionalStop.current = true;
              update({ state: "error", error: (error as Error).message });
              ws.send(JSON.stringify({ type: "stop" }));
            }
            break;
          }
          case "audio.received":
          case "audio.stopped": {
            const tracksMetrics = (event.tracks ?? {}) as Record<string, { bytes: number; duration: number }>;
            const seconds = Math.max(0, ...Object.values(tracksMetrics).map((track) => track.duration));
            const bytes = Object.fromEntries(Object.entries(tracksMetrics).map(([name, track]) => [name, track.bytes]));
            update({ seconds, bytes });
            break;
          }
          case "capture.error":
            if (event.code === "AGENT_DISCONNECTED") {
              // The agent is gone: the recording is not being fed. The stored audio can still
              // be finalized from the meeting page.
              intentionalStop.current = true;
              closeLevels();
              update({ state: "error", error: event.code, levels: {} });
              ws.close();
              changed.current();
            } else {
              update({ error: event.code });
            }
            break;
          case "transcript.queued":
          case "transcript.failed":
            session.current = null;
            closeLevels();
            setStatus((current) => ({
              ...current,
              state: current.state === "error" ? "error" : "stopped",
              levels: {},
              history: {},
              error: current.error ?? (event.type === "transcript.failed" ? event.code : null),
            }));
            ws.close();
            changed.current();
            break;
          case "audio.error":
            if (
              ["MEETING_BUSY", "MEETING_NOT_FOUND", "SESSION_NOT_RECOVERABLE", "MEETING_ALREADY_RECORDED"].includes(
                event.code,
              )
            ) {
              intentionalStop.current = true;
              update({ state: "error", error: event.code });
              ws.close();
            }
            break;
        }
      };
      ws.onclose = () => {
        if (socket.current !== ws || !session.current) return;
        if (intentionalStop.current || attempts.current >= MAX_RECONNECT_ATTEMPTS) {
          // Keep an explicit error (for example a lost agent) visible instead of masking it.
          setStatus((current) => (current.state === "error" ? current : { ...current, state: "disconnected" }));
          return;
        }
        // The agent keeps streaming to the backend; only the event channel is resumed.
        attempts.current += 1;
        update({ state: "reconnecting" });
        const delay = Math.min(8000, 500 * 2 ** (attempts.current - 1));
        window.setTimeout(() => {
          if (session.current) connect({ type: "start", resume: true, session_id: session.current, next_sequence: 0 }, tracks);
        }, delay);
      };
    },
    [meetingId],
  );

  const start = useCallback(
    (tracks: AgentTrack[]) => {
      intentionalStop.current = false;
      attempts.current = 0;
      update({ state: "connecting", error: null, seconds: 0, levels: {}, history: {}, bytes: {} });
      connect({ type: "start", source: "agent" }, tracks);
    },
    [connect],
  );

  const stop = useCallback(() => {
    intentionalStop.current = true;
    update({ state: "stopping" });
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
  }, []);

  useEffect(
    () => () => {
      intentionalStop.current = true;
      session.current = null;
      socket.current?.close();
      closeLevels();
    },
    [],
  );

  return { status, start, stop };
}
