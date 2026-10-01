import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, describeError, type Segment, type Transcription } from "../../api";
import { formatTimestamp, STATUS_LABELS, TRACK_LABELS } from "../../format";
import { BrainPanel } from "./BrainPanel";
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
  const { meetingId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [importing, setImporting] = useState(false);
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
  const scrollToSegment = (id: string, behavior: ScrollBehavior = "auto") => {
    autoScrollUntil.current = performance.now() + 1200;
    document.getElementById(`segment-${id}`)?.scrollIntoView({ block: "center", behavior });
  };
  useEffect(() => {
    const userMoved = () => setFollow(false);
    const onScroll = () => {
      if (performance.now() >= autoScrollUntil.current) setFollow(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (["PageUp", "PageDown", "Home", "End", "ArrowUp", "ArrowDown"].includes(event.key)) setFollow(false);
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
    };
  }, []);

  // Keep the segment being played in view ("Autoscroll con audio activo" in the design).
  useEffect(() => {
    if (!follow || !current) return;
    scrollToSegment(current, "smooth");
  }, [current, follow]);

  // Deep link from a Memory source: /meetings/{id}?at=<seconds>&segment=<id> highlights the
  // definitive segment and positions the audio at the cited second (brain-memoria-global.md).
  const linkedSegment = searchParams.get("segment");
  const linkedAt = Number(searchParams.get("at") ?? "NaN");
  const linkedPlay = searchParams.get("play") === "1";
  useEffect(() => {
    const segment = transcript.data?.segments.find((item) => item.id === linkedSegment);
    if (!segment) return;
    setSelected(segment.id);
    scrollToSegment(segment.id);
    // Every track moves to the cited second; it starts playing only when the link asks for it
    // (Memory sources do), otherwise the user presses play.
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

  if (meeting.isPending) return <p>Cargando reunión…</p>;
  if (meeting.isError) return <p role="alert">No se encontró la reunión.</p>;

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
              <span className="visually-hidden">Título</span>
              <input value={draftTitle} maxLength={200} onChange={(e) => setDraftTitle(e.target.value)} />
            </label>
            <button type="submit" disabled={!draftTitle.trim() || rename.isPending}>
              Guardar
            </button>
            <button type="button" onClick={() => setEditing(false)}>
              Cancelar
            </button>
          </form>
        ) : (
          <h1>{data.title}</h1>
        )}
        <div className="row">
          <button type="button" disabled={busy} onClick={() => setImporting(true)}>
            Importar
          </button>
          {!editing && (
            <button
              type="button"
              onClick={() => {
                setDraftTitle(data.title);
                setEditing(true);
              }}
            >
              Renombrar
            </button>
          )}
          {confirmDelete ? (
            <>
              <button type="button" className="danger" onClick={() => remove.mutate()}>
                Confirmar borrado
              </button>
              <button type="button" onClick={() => setConfirmDelete(false)}>
                Cancelar
              </button>
            </>
          ) : (
            <button type="button" className="danger" onClick={() => setConfirmDelete(true)}>
              Borrar
            </button>
          )}
        </div>
      </header>
      {remove.isError && <p role="alert">No se pudo borrar la reunión.</p>}

      <MeetingTags meetingId={meetingId} tags={data.tags} />
      <MeetingBacklinks meetingId={meetingId} />

      <dl className="facts">
        <dt>Estado</dt>
        <dd data-testid="meeting-status">{STATUS_LABELS[data.status]}</dd>
        <dt>Duración</dt>
        <dd>{data.duration === null ? "—" : formatTimestamp(data.duration)}</dd>
        <dt>Idiomas</dt>
        <dd>{data.primary_language.join(", ") || "—"}</dd>
        <dt>Asistentes</dt>
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

      <MeetingNotes meetingId={meetingId} focusBlock={searchParams.get("note")} />

      <SyncedPlayer
        ref={player}
        meetingId={meetingId}
        tracks={data.tracks}
        version={transcription.data?.job_id ?? null}
        onTimeChange={setPlayhead}
        onPlay={() => setFollow(true)}
      />

      <BrainPanel
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

      <MeetingSpeakers meetingId={meetingId} hasTranscript={Boolean(transcript.data)} />

      <div className="row transcript-heading">
        <h2>Transcript definitivo</h2>
        {transcript.data && data.tracks.length > 0 && (
          <button
            type="button"
            aria-pressed={follow}
            onClick={() => setFollow((value) => !value)}
            title="Desplaza el transcript para mantener a la vista el fragmento que suena"
          >
            {follow ? "Siguiendo la reproducción" : "Seguir la reproducción"}
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
                  {formatTimestamp(segment.start)} · {TRACK_LABELS[segment.track]} ·{" "}
                  <span title={segment.person ? segment.speaker ?? undefined : undefined}>
                    {segment.person ?? segment.speaker ?? "Hablante no disponible"}
                  </span>{" "}
                  · Idioma:{" "}
                  {segment.language ?? "no disponible"}
                </span>
                <span className="text">{segment.text}</span>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p>{busy ? "El transcript aparecerá cuando termine la transcripción." : "Sin transcript definitivo."}</p>
      )}

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

const STAGE_LABELS: Record<string, string> = {
  transcribing: "Transcribiendo",
  fallback: "Transcribiendo con el proveedor de respaldo",
  finalizing: "Finalizando",
  retrying: "Reintentando",
  requeued: "Reencolado",
  completed: "Completado",
  failed: "Fallido",
};

function TranscriptionStatus({ job }: { job: Transcription | null | undefined }) {
  if (!job) return null;
  if (job.status === "failed") {
    return (
      <p role="alert" className="transcription-failed">
        Transcripción fallida: {describeError(job.error)}
      </p>
    );
  }
  if (job.status === "completed") return null;
  const percent = Math.round(job.progress * 100);
  const trackLabel = job.track ? TRACK_LABELS[job.track] ?? job.track : null;
  const current = Math.min(job.processed_tracks + 1, job.total_tracks);
  return (
    <div role="status" aria-live="polite" className="transcription-progress" data-testid="transcription-progress">
      <p>
        {job.status === "queued" ? "En cola" : (STAGE_LABELS[job.stage ?? ""] ?? "Procesando")}
        {trackLabel && job.total_tracks > 0 && ` · pista ${trackLabel} (${current} de ${job.total_tracks})`} ·{" "}
        {percent} %
      </p>
      <progress value={job.progress} max={1} />
    </div>
  );
}
