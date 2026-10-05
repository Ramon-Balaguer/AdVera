import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, describeError, type Segment, type Transcription } from "../../api";
import { formatTimestamp, statusLabel, trackLabel } from "../../format";
import { MeetingBrain } from "./MeetingBrain";
import { SummaryPanel } from "./SummaryPanel";
import { CaptureControls } from "./CaptureControls";
import { MeetingBacklinks } from "./MeetingBacklinks";
import { MeetingImportModal } from "./MeetingImportModal";
import { clearNotesDraft, MeetingNotes } from "./MeetingNotes";
import { MeetingSpeakers } from "./MeetingSpeakers";
import { MeetingTags } from "./MeetingTags";
import { SyncedPlayer, type SyncedPlayerHandle } from "./SyncedPlayer";

// ADR 0004: bounded polling of the durable HTTP status is the fallback when no socket exists.
const POLL_MS = 2000;
const isActive = (job: Transcription | null | undefined) =>
  job?.status === "queued" || job?.status === "running";

export function MeetingPage() {
  const { t } = useTranslation();
  const { meetingId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [importing, setImporting] = useState(false);
  const [sideTab, setSideTab] = useState<"summary" | "brain">("summary");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  // `selected` is the segment chosen explicitly (click, citation, deep link); once the player
  // reports a position, the highlight follows the playhead instead.
  const [selected, setSelected] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [follow, setFollow] = useState(true);
  const player = useRef<SyncedPlayerHandle>(null);

  const meeting = useQuery({ queryKey: ["meeting", meetingId], queryFn: () => api.getMeeting(meetingId) });
  const transcription = useQuery({
    queryKey: ["transcription", meetingId],
    queryFn: () => api.getTranscription(meetingId),
    refetchInterval: (query) => (isActive(query.state.data) ? POLL_MS : false),
  });
  const transcript = useQuery({
    queryKey: ["transcript", meetingId],
    queryFn: () => api.getTranscript(meetingId),
  });

  // Segments under the playhead (transcript-card-review-ui.md: "The active segment is visually
  // distinguished during playback"). Tracks overlap, so several can be active at once; in a
  // silence the last segment that started stays active. `current` is the one to scroll to.
  // The explicitly chosen segment also counts from up to 1 s before its start, because
  // citation links carry whole seconds (?at=12 for a segment at 12.4 s).
  const { activeIds, current } = useMemo(() => {
    const segments = transcript.data?.segments ?? [];
    if (playhead === null) return { activeIds: new Set(selected ? [selected] : []), current: null };
    let active = segments.filter((segment) => segment.start <= playhead && playhead < segment.end);
    const chosen = segments.find((segment) => segment.id === selected);
    if (chosen && chosen.start - 1 <= playhead && playhead < chosen.end) {
      active = [chosen, ...active.filter((segment) => segment.id !== chosen.id)];
      return { activeIds: new Set(active.map((segment) => segment.id)), current: chosen.id };
    }
    if (active.length === 0) {
      const started = segments.filter((segment) => segment.start <= playhead);
      const latest = started.reduce<Segment | null>((best, s) => (!best || s.start > best.start ? s : best), null);
      active = latest ? [latest] : [];
    }
    const latest = active.reduce<Segment | null>((best, s) => (!best || s.start > best.start ? s : best), null);
    return { activeIds: new Set(active.map((segment) => segment.id)), current: latest?.id ?? null };
  }, [transcript.data, playhead, selected]);

  // A chosen segment only overrides the playhead while the playhead is still around it; once
  // the audio moves on (or the user scrubs elsewhere) the highlight follows the playhead again.
  useEffect(() => {
    const chosen = transcript.data?.segments.find((segment) => segment.id === selected);
    if (playhead !== null && chosen && !(chosen.start - 1 <= playhead && playhead < chosen.end)) {
      setSelected(null);
    }
  }, [playhead, selected, transcript.data]);

  // Scrolling by hand turns "seguir la reproducción" off, and the user is free to move until
  // they turn it back on or press play again. The page's own scrolling (smooth scrollIntoView)
  // must not count as the user's, so it opens a short window in which scroll events are ignored;
  // wheel, touch and scroll keys are always the user's.
  const autoScrollUntil = useRef(0);
  // The smooth scroll is animated here, not by the browser: a browser smooth scroll still in
  // flight when the user moves the wheel wins over the gesture and drags the page back. This one
  // is cancelled by any wheel, touch or scroll key.
  const animation = useRef<number | null>(null);
  const stopAnimation = () => {
    if (animation.current !== null) cancelAnimationFrame(animation.current);
    animation.current = null;
  };
  const scrollToSegment = (id: string, behavior: ScrollBehavior = "auto") => {
    const element = document.getElementById(`segment-${id}`);
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const target = Math.max(0, Math.min(max, window.scrollY + rect.top - (window.innerHeight - rect.height) / 2));
    stopAnimation();
    const duration = behavior === "smooth" ? 450 : 0;
    autoScrollUntil.current = performance.now() + duration + 300;
    if (!duration) {
      window.scrollTo({ top: target, behavior: "instant" });
      return;
    }
    const start = window.scrollY;
    const began = performance.now();
    const step = (now: number) => {
      const progress = Math.min(1, (now - began) / duration);
      window.scrollTo({ top: start + (target - start) * (1 - (1 - progress) ** 3), behavior: "instant" });
      animation.current = progress < 1 ? requestAnimationFrame(step) : null;
    };
    animation.current = requestAnimationFrame(step);
  };
  useEffect(() => {
    const userMoved = () => {
      stopAnimation(); // the user's gesture takes over at once
      setFollow(false);
    };
    const onScroll = () => {
      if (performance.now() >= autoScrollUntil.current) setFollow(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (["PageUp", "PageDown", "Home", "End", "ArrowUp", "ArrowDown"].includes(event.key)) userMoved();
    };
    window.addEventListener("wheel", userMoved, { passive: true });
    window.addEventListener("touchmove", userMoved, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("wheel", userMoved);
      window.removeEventListener("touchmove", userMoved);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("keydown", onKey);
      stopAnimation();
    };
  }, []);

  // Keep the segment being played in view ("Autoscroll con audio activo" in the design).
  useEffect(() => {
    if (!follow || !current) return;
    scrollToSegment(current, "smooth");
  }, [current, follow]);

  // Deep link from a Brain source: /meetings/{id}?at=<seconds>&segment=<id> highlights the
  // definitive segment and positions the audio at the cited second (brain-global.md).
  const linkedSegment = searchParams.get("segment");
  const linkedAt = Number(searchParams.get("at") ?? "NaN");
  const linkedPlay = searchParams.get("play") === "1";
  useEffect(() => {
    const segment = transcript.data?.segments.find((item) => item.id === linkedSegment);
    if (!segment) return;
    setSelected(segment.id);
    scrollToSegment(segment.id);
    // Every track moves to the cited second; it starts playing only when the link asks for it
    // (Brain sources do), otherwise the user presses play.
    player.current?.seek(Number.isFinite(linkedAt) ? linkedAt : segment.start, linkedPlay);
  }, [transcript.data, linkedSegment, linkedAt, linkedPlay]);

  // When the durable job finishes, reload the meeting and its definitive transcript.
  const jobState = `${transcription.data?.job_id}:${transcription.data?.status}`;
  useEffect(() => {
    if (transcription.data && !isActive(transcription.data)) {
      void queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
      void queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
    }
  }, [jobState, meetingId, queryClient]);

  const rename = useMutation({
    mutationFn: (title: string) => api.renameMeeting(meetingId, title),
    onSuccess: (updated) => {
      queryClient.setQueryData(["meeting", meetingId], updated);
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
      setEditing(false);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteMeeting(meetingId),
    onSuccess: () => {
      clearNotesDraft(meetingId);
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate("/meetings");
    },
  });

  if (meeting.isPending) return <p>{t("meeting.loading")}</p>;
  if (meeting.isError) return <p role="alert">{t("meeting.notFound")}</p>;

  const data = meeting.data;
  const job = transcription.data;
  const busy = data.status === "processing" || data.status === "recording" || isActive(job);

  // Click-to-seek moves every track to the segment and plays them together, so the
  // microphone and the system audio are heard coherently.
  const playFrom = (segment: Segment) => {
    setSelected(segment.id);
    setFollow(true); // choosing a segment to play is asking to follow it again
    player.current?.seek(segment.start, true);
  };

  return (
    <section>
      <header className="meeting-header">
        {editing ? (
          <form
            className="row"
            onSubmit={(event) => {
              event.preventDefault();
              if (draftTitle.trim()) rename.mutate(draftTitle.trim());
            }}
          >
            <label className="grow">
              <span className="visually-hidden">{t("meeting.titleLabel")}</span>
              <input value={draftTitle} maxLength={200} onChange={(e) => setDraftTitle(e.target.value)} />
            </label>
            <button type="submit" disabled={!draftTitle.trim() || rename.isPending}>
              {t("common.save")}
            </button>
            <button type="button" onClick={() => setEditing(false)}>
              {t("common.cancel")}
            </button>
          </form>
        ) : (
          <h1>{data.title}</h1>
        )}
        <div className="row">
          <button type="button" disabled={busy} onClick={() => setImporting(true)}>
            {t("meeting.import")}
          </button>
          {!editing && (
            <button
              type="button"
              onClick={() => {
                setDraftTitle(data.title);
                setEditing(true);
              }}
            >
              {t("meeting.rename")}
            </button>
          )}
          {confirmDelete ? (
            <>
              <button type="button" className="danger" onClick={() => remove.mutate()}>
                {t("meeting.confirmDelete")}
              </button>
              <button type="button" onClick={() => setConfirmDelete(false)}>
                {t("common.cancel")}
              </button>
            </>
          ) : (
            <button type="button" className="danger" onClick={() => setConfirmDelete(true)}>
              {t("meeting.delete")}
            </button>
          )}
        </div>
      </header>
      {remove.isError && <p role="alert">{t("meeting.deleteError")}</p>}

      <MeetingTags meetingId={meetingId} tags={data.tags} />
      <MeetingBacklinks meetingId={meetingId} />

      <dl className="facts">
        <dt>{t("meeting.factStatus")}</dt>
        <dd data-testid="meeting-status">{statusLabel(data.status)}</dd>
        <dt>{t("meeting.factDuration")}</dt>
        <dd>{data.duration === null ? "—" : formatTimestamp(data.duration)}</dd>
        <dt>{t("meeting.factLanguages")}</dt>
        <dd>{data.primary_language.join(", ") || "—"}</dd>
        <dt>{t("meeting.factAttendees")}</dt>
        <dd>{data.attendee_count ?? "—"}</dd>
      </dl>

      <CaptureControls
        meeting={data}
        jobActive={isActive(job)}
        onChanged={() => {
          void queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
          void queryClient.invalidateQueries({ queryKey: ["transcription", meetingId] });
          void queryClient.invalidateQueries({ queryKey: ["audio-metrics", meetingId] });
          void queryClient.invalidateQueries({ queryKey: ["meetings"] });
        }}
      />

      <TranscriptionStatus job={job} />

      <SyncedPlayer
        ref={player}
        meetingId={meetingId}
        tracks={data.tracks}
        version={transcription.data?.job_id ?? null}
        onTimeChange={setPlayhead}
        onPlay={() => setFollow(true)}
      />

      {/* Transcript on the left, the meeting's intelligence on the right (docs/design). */}
      <div className="meeting-columns">
        <div className="meeting-main">
          <div className="row transcript-heading">
            <h2>{t("meeting.transcriptTitle")}</h2>
            {transcript.data && data.tracks.length > 0 && (
              <button
                type="button"
                aria-pressed={follow}
                onClick={() => setFollow((value) => !value)}
                title={t("meeting.followTitle")}
              >
                {follow ? t("meeting.following") : t("meeting.follow")}
              </button>
            )}
          </div>
          {transcript.data ? (
            <ol className="transcript">
              {transcript.data.segments.map((segment) => (
                <li
                  key={segment.id}
                  id={`segment-${segment.id}`}
                  className={activeIds.has(segment.id) ? "active" : undefined}
                  aria-current={activeIds.has(segment.id) ? "true" : undefined}
                >
                  <button type="button" className="segment" onClick={() => playFrom(segment)}>
                    <span className="meta">
                      {formatTimestamp(segment.start)} · {trackLabel(segment.track)} ·{" "}
                      <span title={segment.person ? segment.speaker ?? undefined : undefined}>
                        {segment.person ?? segment.speaker ?? t("meeting.noSpeaker")}
                      </span>{" "}
                      · {t("meeting.language", { language: segment.language ?? t("meeting.notAvailable") })}
                    </span>
                    <span className="text">{segment.text}</span>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <p>{busy ? t("meeting.transcriptPending") : t("meeting.noTranscript")}</p>
          )}
        </div>
        <aside className="meeting-side" aria-label={t("meeting.columnsSide")}>
          <div className="tabs" role="tablist" aria-label={t("meetingBrain.tabs")}>
            {(["summary", "brain"] as const).map((tab) => (
              <button
                key={tab}
                role="tab"
                type="button"
                aria-selected={sideTab === tab}
                className={sideTab === tab ? "active" : ""}
                onClick={() => setSideTab(tab)}
              >
                {t(tab === "summary" ? "meetingBrain.tabSummary" : "meetingBrain.tabBrain")}
              </button>
            ))}
          </div>
          {sideTab === "brain" && <MeetingBrain meetingId={meetingId} />}
          {sideTab === "summary" && (
          <SummaryPanel
            meetingId={meetingId}
            onSeek={(segmentId) => {
              if (segmentId.startsWith("note-")) {
                setSearchParams({ note: segmentId }, { replace: true }); // a cited note block
                return;
              }
              const segment = transcript.data?.segments.find((item) => item.id === segmentId);
              if (segment) {
                playFrom(segment);
                scrollToSegment(segment.id);
              }
            }}
          />
          )}
          <MeetingSpeakers meetingId={meetingId} hasTranscript={Boolean(transcript.data)} />
          <MeetingNotes meetingId={meetingId} focusBlock={searchParams.get("note")} />
        </aside>
      </div>

      {importing && (
        <MeetingImportModal
          meetingId={meetingId}
          onClose={() => setImporting(false)}
          onImported={() => {
            setImporting(false);
            void queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
            void queryClient.invalidateQueries({ queryKey: ["transcription", meetingId] });
            void queryClient.invalidateQueries({ queryKey: ["meetings"] });
          }}
        />
      )}
    </section>
  );
}

const STAGES = ["transcribing", "fallback", "finalizing", "retrying", "requeued", "completed", "failed"] as const;

function TranscriptionStatus({ job }: { job: Transcription | null | undefined }) {
  const { t } = useTranslation();
  if (!job) return null;
  if (job.status === "failed") {
    return (
      <p role="alert" className="transcription-failed">
        {t("transcription.failed", { reason: describeError(job.error) })}
      </p>
    );
  }
  if (job.status === "completed") return null;
  const percent = Math.round(job.progress * 100);
  const currentTrack = job.track ? trackLabel(job.track) : null;
  const current = Math.min(job.processed_tracks + 1, job.total_tracks);
  return (
    <div role="status" aria-live="polite" className="transcription-progress" data-testid="transcription-progress">
      <p>
        {job.status === "queued"
          ? t("transcription.queued")
          : (STAGES as readonly string[]).includes(job.stage ?? "")
            ? t(`transcription.stage.${job.stage as (typeof STAGES)[number]}`)
            : t("transcription.processing")}
        {currentTrack &&
          job.total_tracks > 0 &&
          t("transcription.track", { track: currentTrack, current, total: job.total_tracks })}{" "}
        ·{" "}
        {percent} %
      </p>
      <progress value={job.progress} max={1} />
    </div>
  );
}
