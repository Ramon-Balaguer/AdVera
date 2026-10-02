import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { api, describeError, type Meeting } from "../../api";
import { formatTimestamp, trackLabel } from "../../format";
import { LiveWaveform } from "./LiveWaveform";
import { type AgentTrack, useAgentCapture } from "./useAgentCapture";
import { type CaptureState, useMicrophoneCapture } from "./useMicrophoneCapture";

const LIVE: CaptureState[] = ["connecting", "recording", "reconnecting", "stopping"];

const capabilitiesSchema = z.object({
  available: z.boolean(),
  platform: z.string().optional(),
  tracks: z.record(z.string(), z.object({ state: z.string() })),
});

async function fetchCapabilities() {
  const response = await fetch("/api/capture-agent/capabilities");
  if (!response.ok) return { available: false, tracks: {} };
  return capabilitiesSchema.parse(await response.json());
}

/**
 * Capture controls. The desktop agent records `microphone` and `system` as independent
 * tracks (ADR 0005, 0010); the browser microphone is the fallback when no agent is connected.
 */
export function CaptureControls({
  meeting,
  jobActive,
  onChanged,
}: {
  meeting: Meeting;
  jobActive: boolean;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const browser = useMicrophoneCapture(meeting.id, onChanged);
  const agent = useAgentCapture(meeting.id, onChanged);
  const browserLive = LIVE.includes(browser.status.state);
  const agentLive = LIVE.includes(agent.status.state);
  const live = browserLive || agentLive;

  const capabilities = useQuery({
    queryKey: ["capture-agent-capabilities"],
    queryFn: fetchCapabilities,
    refetchInterval: live ? false : 10_000,
  });
  const agentTracks = Object.entries(capabilities.data?.tracks ?? {})
    .filter(([, track]) => track.state === "available")
    .map(([name]) => name as AgentTrack);
  const agentReady = Boolean(capabilities.data?.available) && agentTracks.length > 0;

  // A recording left by a lost tab or a restart is recoverable from its durable cursor.
  const interrupted = meeting.status === "recording" && !live;
  const metrics = useQuery({
    queryKey: ["audio-metrics", meeting.id],
    queryFn: () => api.getAudioMetrics(meeting.id),
    enabled: interrupted,
  });
  // Also offered for a *stopped* session whose meeting is still "recording": the stop never
  // reached the meeting, and resuming it finishes the stop on the backend.
  const recover = metrics.data
    ? { sessionId: metrics.data.session_id, nextSequence: metrics.data.next_sequence }
    : undefined;
  const sessionStillOpen = metrics.data?.status === "recording";
  // A recording owned by the desktop agent cannot be continued with the browser microphone:
  // the backend would reject every frame. It can only be finalized with the audio it has.
  const agentOwned = Boolean(metrics.data?.capture_session_id);
  // Audio already stored is never replaced: another recording belongs to another meeting.
  const alreadyRecorded = meeting.tracks.length > 0;
  const canRecord =
    !live && !jobActive && meeting.status !== "processing" && !interrupted && !alreadyRecorded;
  const status = agentLive || agent.status.state !== "idle" ? agent.status : browser.status;

  return (
    <section className="capture" aria-label={t("capture.region")}>
      <div className="row">
        {agentLive && (
          <button type="button" className="rec active" onClick={agent.stop} disabled={agent.status.state === "stopping"}>
            {t("capture.stop")}
          </button>
        )}
        {browserLive && (
          <button type="button" className="rec active" onClick={browser.stop} disabled={browser.status.state === "stopping"}>
            {t("capture.stop")}
          </button>
        )}
        {!live && agentReady && (
          <button type="button" className="rec" disabled={!canRecord} onClick={() => agent.start(agentTracks)}>
            {t("capture.recordAgent", {
              tracks: agentTracks.map((track) => trackLabel(track).toLowerCase()).join(" + "),
            })}
          </button>
        )}
        {!live && (
          <button type="button" className={agentReady ? "" : "rec"} disabled={!canRecord} onClick={() => void browser.start()}>
            {agentReady ? t("capture.recordBrowserMic") : t("capture.recordMic")}
          </button>
        )}
        {interrupted && recover && (
          <>
            {!agentOwned && sessionStillOpen && (
              <button type="button" onClick={() => void browser.start(recover)}>
                {t("capture.continue")}
              </button>
            )}
            <button type="button" onClick={() => browser.finalize(recover)}>
              {t("capture.finalize")}
            </button>
          </>
        )}
        {status.state !== "idle" && (
          <span role="status" aria-live="polite" data-testid="capture-state">
            {t(`capture.state.${status.state}`)}
          </span>
        )}
        {live && <span className="clock">{formatTimestamp(status.seconds)}</span>}
      </div>

      {!live && !agentReady && (
        <p className="hint">{t("capture.noAgent")}</p>
      )}
      {browserLive && (
        <LiveWaveform label={trackLabel("microphone")} track="microphone" levels={browser.status.history} />
      )}
      {agentLive &&
        (["microphone", "system"] as AgentTrack[])
          .filter((track) => agentTracks.includes(track))
          .map((track) => (
            <div key={track}>
              <LiveWaveform label={trackLabel(track)} track={track} levels={agent.status.history[track] ?? []} />
              <span className="track-bytes" data-testid={`agent-bytes-${track}`}>
                {((agent.status.bytes[track] ?? 0) / 1024).toFixed(0)} KiB
              </span>
            </div>
          ))}
      {alreadyRecorded && !live && !interrupted && (
        <p className="hint" data-testid="already-recorded">
          {t("capture.alreadyRecorded")}
        </p>
      )}
      {interrupted && !live && (
        <p className="hint">{t("capture.interrupted")}</p>
      )}
      {status.error && <p role="alert">{describeError(status.error)}</p>}
    </section>
  );
}
