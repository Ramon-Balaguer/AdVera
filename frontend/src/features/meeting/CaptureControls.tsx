import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { api, describeError, type Meeting } from "../../api";
import { formatTimestamp, trackLabel } from "../../format";
import { LiveWaveform } from "./LiveWaveform";
import { type AgentTrack, useAgentCapture } from "./useAgentCapture";
import { useMeetingBot } from "./useMeetingBot";
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
 * The meeting bot (ADR 0026) is a fourth source: it joins a Google Meet or Teams call and its
 * audio arrives as the `system` track when it leaves. One source per meeting.
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
  const meetingBot = useMeetingBot(meeting.id, onChanged);
  const [botForm, setBotForm] = useState(false);
  const [meetUrl, setMeetUrl] = useState("");
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

  // A meeting the bot owns is "recording" while the bot is in the call: it is not interrupted,
  // and no other source may start (the backend would refuse it with MEETING_BUSY).
  const botOwned = meetingBot.owns;
  // A recording left by a lost tab or a restart is recoverable from its durable cursor.
  const interrupted = meeting.status === "recording" && !live && !botOwned;
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
    !live &&
    !botOwned &&
    !jobActive &&
    meeting.status !== "processing" &&
    !interrupted &&
    !alreadyRecorded;
  const botName = meetingBot.capabilities?.bot_name ?? "AdVera Notekeeper";
  const botReady = Boolean(meetingBot.capabilities?.configured && meetingBot.capabilities.available);
  const bot = meetingBot.bot;
  // Audio already stored is never replaced, so there is nothing to offer: the section is hidden.
  if (alreadyRecorded && !live && !interrupted && !botOwned) return null;

  const sendBot = (event: FormEvent) => {
    event.preventDefault();
    meetingBot.start.mutate(meetUrl.trim(), {
      onSuccess: () => {
        setBotForm(false);
        setMeetUrl("");
      },
    });
  };
  const botError = meetingBot.start.error ?? meetingBot.stop.error;
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
        {botOwned && bot && (
          <>
            <span role="status" aria-live="polite" data-testid="bot-state">
              {t("capture.bot.in", { name: bot.bot_name, platform: t(`capture.bot.platform.${bot.platform}`) })}
              {" · "}
              {t(`capture.bot.state.${bot.status}`)}
            </span>
            {meetingBot.inCall && bot.status !== "stopping" && (
              <button
                type="button"
                className="rec active"
                data-testid="bot-leave"
                onClick={() => meetingBot.stop.mutate()}
                disabled={meetingBot.stop.isPending}
              >
                {t("capture.bot.leave")}
              </button>
            )}
          </>
        )}
        {!live && !botOwned && agentReady && (
          <button type="button" className="rec" disabled={!canRecord} onClick={() => agent.start(agentTracks)}>
            {t("capture.recordAgent", {
              tracks: agentTracks.map((track) => trackLabel(track).toLowerCase()).join(" + "),
            })}
          </button>
        )}
        {!live && !botOwned && (
          <button type="button" className={agentReady ? "" : "rec"} disabled={!canRecord} onClick={() => void browser.start()}>
            {agentReady ? t("capture.recordBrowserMic") : t("capture.recordMic")}
          </button>
        )}
        {!live && !botOwned && botReady && !botForm && (
          <button type="button" data-testid="bot-send" disabled={!canRecord} onClick={() => setBotForm(true)}>
            {t("capture.bot.send", { name: botName })}
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

      {botForm && !botOwned && (
        <form className="bot-form row" onSubmit={sendBot}>
          <label htmlFor="meet-url">{t("capture.bot.urlLabel")}</label>
          <input
            id="meet-url"
            data-testid="bot-url"
            type="url"
            required
            autoFocus
            value={meetUrl}
            placeholder={t("capture.bot.urlPlaceholder")}
            onChange={(event) => setMeetUrl(event.target.value)}
          />
          <button
            type="submit"
            className="rec"
            data-testid="bot-confirm"
            disabled={meetingBot.start.isPending || !meetUrl.trim()}
          >
            {t("capture.bot.confirm")}
          </button>
          <button type="button" onClick={() => setBotForm(false)}>
            {t("common.cancel")}
          </button>
          <p className="hint">{t("capture.bot.hint")}</p>
        </form>
      )}
      {botOwned && bot?.status === "active" && bot.consent_notice === "unsupported" && (
        <p className="hint" data-testid="bot-consent">{t("capture.bot.consentUnsupported")}</p>
      )}
      {botOwned && bot?.status === "active" && bot.consent_notice === "sent" && (
        <p className="hint" data-testid="bot-consent">{t("capture.bot.consentSent")}</p>
      )}
      {!botOwned && bot?.status === "failed" && (
        <p role="alert">{describeError(bot.error ?? "BOT_FAILED")}</p>
      )}
      {botError && <p role="alert">{describeError(botError.message)}</p>}
      {meetingBot.capabilities?.configured && !meetingBot.capabilities.available && !botOwned && (
        <p className="hint">{t("capture.bot.unavailable")}</p>
      )}
      {!live && !botOwned && !agentReady && (
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
      {interrupted && !live && (
        <p className="hint">{t("capture.interrupted")}</p>
      )}
      {status.error && <p role="alert">{describeError(status.error)}</p>}
    </section>
  );
}
