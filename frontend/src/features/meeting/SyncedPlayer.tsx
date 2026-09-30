import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

import { api, type Track } from "../../api";
import { formatTimestamp } from "../../format";

// Synchronized playback of every stored track (dual-track-playback-live-metrics.md: "plays
// both tracks together"). One transport drives all tracks; the longest track is the master
// clock and the others follow it, correcting any drift above DRIFT_TOLERANCE. Tracks stay
// independent files (ADR 0005): they are aligned on the recording timeline, never mixed.

const DRIFT_TOLERANCE = 0.08;
const SYNC_INTERVAL_MS = 250;

export interface SyncedPlayerHandle {
  /** Move every track to `seconds`; optionally start playing all of them together. */
  seek: (seconds: number, play?: boolean) => void;
}

interface TrackState {
  muted: boolean;
  volume: number;
}

interface SyncedPlayerProps {
  meetingId: string;
  tracks: Track[];
  /** Changes when the stored audio is replaced (a new import), so stale audio is reloaded. */
  version?: string | number | null;
  /** Called with the meeting position after every seek and on every sync tick while playing. */
  onTimeChange?: (seconds: number) => void;
}

export const SyncedPlayer = forwardRef<SyncedPlayerHandle, SyncedPlayerProps>(
  function SyncedPlayer({ meetingId, tracks, version, onTimeChange }, ref) {
    const elements = useRef<Partial<Record<Track, HTMLAudioElement | null>>>({});
    const pendingSeek = useRef<{ seconds: number; play: boolean } | null>(null);
    // A track whose audio cannot be loaded is left out, so one broken file does not stop the
    // others from playing or make every click-to-seek wait for metadata that never arrives.
    const failed = useRef<Set<Track>>(new Set());
    const [playing, setPlaying] = useState(false);
    const [time, setTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [trackState, setTrackState] = useState<Partial<Record<Track, TrackState>>>({});
    const onTime = useRef(onTimeChange);
    onTime.current = onTimeChange;

    const all = useCallback(
      () =>
        tracks
          .filter((track) => !failed.current.has(track))
          .map((track) => elements.current[track])
          .filter((el): el is HTMLAudioElement => Boolean(el)),
      [tracks],
    );

    const master = useCallback((): HTMLAudioElement | undefined => {
      const list = all();
      return list.reduce<HTMLAudioElement | undefined>(
        (longest, el) => (!longest || (el.duration || 0) > (longest.duration || 0) ? el : longest),
        undefined,
      );
    }, [all]);

    const ready = useCallback(() => all().length > 0 && all().every((el) => el.readyState >= 1), [all]);

    const setAllTimes = useCallback(
      (seconds: number) => {
        for (const el of all()) {
          const limit = Number.isFinite(el.duration) ? el.duration : seconds;
          el.currentTime = Math.max(0, Math.min(seconds, limit));
        }
        setTime(seconds);
        onTime.current?.(seconds);
      },
      [all],
    );

    const playAll = useCallback(async () => {
      const clock = master();
      if (!clock) return;
      setAllTimes(clock.currentTime);
      await Promise.all(
        all()
          .filter((el) => el.currentTime < (el.duration || Infinity))
          .map((el) => el.play().catch(() => undefined)),
      );
      setPlaying(true);
    }, [all, master, setAllTimes]);

    const pauseAll = useCallback(() => {
      for (const el of all()) el.pause();
      setPlaying(false);
    }, [all]);

    const seek = useCallback(
      (seconds: number, play = false) => {
        if (!ready()) {
          pendingSeek.current = { seconds, play };
          return;
        }
        setAllTimes(seconds);
        if (play) void playAll();
      },
      [playAll, ready, setAllTimes],
    );

    useImperativeHandle(ref, () => ({ seek }), [seek]);

    // Apply a seek requested before metadata was available (for example a deep link).
    const onMetadata = () => {
      const clock = master();
      if (clock && Number.isFinite(clock.duration)) setDuration(clock.duration);
      if (pendingSeek.current && ready()) {
        const { seconds, play } = pendingSeek.current;
        pendingSeek.current = null;
        seek(seconds, play);
      }
    };

    // Follow the master clock and correct drift while playing.
    useEffect(() => {
      if (!playing) return;
      const timer = window.setInterval(() => {
        const clock = master();
        if (!clock) return;
        setTime(clock.currentTime);
        onTime.current?.(clock.currentTime);
        for (const el of all()) {
          if (el === clock || !Number.isFinite(el.duration)) continue;
          if (el.readyState < 3) continue; // still buffering: seeking it again only stalls it more
          if (clock.currentTime >= el.duration) continue; // shorter track already finished
          if (Math.abs(el.currentTime - clock.currentTime) > DRIFT_TOLERANCE) {
            el.currentTime = clock.currentTime;
          }
          if (el.paused && !clock.paused) void el.play().catch(() => undefined);
        }
        if (clock.paused || clock.ended) pauseAll();
      }, SYNC_INTERVAL_MS);
      return () => window.clearInterval(timer);
    }, [playing, all, master, pauseAll]);

    const updateTrack = (track: Track, patch: Partial<TrackState>) => {
      setTrackState((current) => {
        const next = { muted: false, volume: 1, ...current[track], ...patch };
        const el = elements.current[track];
        if (el) {
          el.muted = next.muted;
          el.volume = next.volume;
        }
        return { ...current, [track]: next };
      });
    };

    if (tracks.length === 0) return null;

    return (
      <section className="synced-player" aria-label="Reproductor de la reunión">
        {tracks.map((track) => (
          <audio
            key={`${track}-${version ?? ""}`}
            preload="metadata"
            src={api.audioUrl(meetingId, track)}
            ref={(element) => {
              elements.current[track] = element;
            }}
            onLoadedMetadata={onMetadata}
            onError={() => {
              failed.current.add(track);
              onMetadata(); // a queued seek may now be applicable to the tracks that did load
            }}
            data-testid={`audio-${track}`}
          />
        ))}
        <div className="row">
          <button
            type="button"
            className="transport"
            onClick={() => (playing ? pauseAll() : void playAll())}
            aria-label={playing ? "Pausar todas las pistas" : "Reproducir todas las pistas"}
          >
            {playing ? "❚❚" : "▶"}
          </button>
          <span className="clock" data-testid="player-time">
            {formatTimestamp(time)} / {formatTimestamp(duration)}
          </span>
          <input
            className="grow"
            type="range"
            min={0}
            max={duration || 0}
            step={0.1}
            value={Math.min(time, duration || 0)}
            onChange={(event) => seek(Number(event.target.value), playing)}
            aria-label="Posición de la reunión"
          />
        </div>
        <div className="row track-mixer">
          {tracks.map((track) => {
            const state = { muted: false, volume: 1, ...trackState[track] };
            const label = track === "microphone" ? "Micrófono" : "Sistema";
            return (
              <span key={track} className="track-control">
                <button
                  type="button"
                  aria-pressed={state.muted}
                  onClick={() => updateTrack(track, { muted: !state.muted })}
                  aria-label={`${state.muted ? "Activar" : "Silenciar"} ${label}`}
                >
                  {state.muted ? "🔇" : "🔊"} {label}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={state.volume}
                  onChange={(event) => updateTrack(track, { volume: Number(event.target.value) })}
                  aria-label={`Volumen ${label}`}
                />
              </span>
            );
          })}
        </div>
      </section>
    );
  },
);
