import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, describeError, type Segment, type Track, type Transcription } from "../../api";
import { formatTimestamp, STATUS_LABELS, TRACK_LABELS } from "../../format";
import { BrainPanel } from "./BrainPanel";
import { CaptureControls } from "./CaptureControls";
import { MeetingImportModal } from "./MeetingImportModal";

// ADR 0004: bounded polling of the durable HTTP status is the fallback when no socket exists.
const POLL_MS = 2000;
const isActive = (job: Transcription | null | undefined) =>
  job?.status === "queued" || job?.status === "running";

export function MeetingPage() {
  const { meetingId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [importing, setImporting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [activeSegment, setActiveSegment] = useState<string | null>(null);
  const audioRefs = useRef<Partial<Record<Track, HTMLAudioElement | null>>>({});

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

  // Deep link from a Memory source: /meetings/{id}?at=<seconds>&segment=<id> highlights the
  // definitive segment and positions the audio at the cited second (brain-memoria-global.md).
  const linkedSegment = searchParams.get("segment");
  const linkedAt = Number(searchParams.get("at") ?? "NaN");
  useEffect(() => {
    const segment = transcript.data?.segments.find((item) => item.id === linkedSegment);
    if (!segment) return;
    setActiveSegment(segment.id);
    document.getElementById(`segment-${segment.id}`)?.scrollIntoView({ block: "center" });
    const audio = audioRefs.current[segment.track];
    if (!audio) return;
    const seek = () => {
      audio.currentTime = Number.isFinite(linkedAt) ? linkedAt : segment.start;
    };
    if (audio.readyState >= 1) seek();
    else audio.addEventListener("loadedmetadata", seek, { once: true });
  }, [transcript.data, linkedSegment, linkedAt]);

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
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate("/meetings");
    },
  });

  if (meeting.isPending) return <p>Cargando reunión…</p>;
  if (meeting.isError) return <p role="alert">No se encontró la reunión.</p>;

  const data = meeting.data;
  const job = transcription.data;
  const busy = data.status === "processing" || data.status === "recording" || isActive(job);

  const playFrom = (segment: Segment) => {
    setActiveSegment(segment.id);
    for (const [track, element] of Object.entries(audioRefs.current)) {
      if (track !== segment.track) element?.pause();
    }
    const audio = audioRefs.current[segment.track];
    if (!audio) return;
    audio.currentTime = segment.start;
    void audio.play().catch(() => undefined);
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

      {data.tracks.map((track) => (
        <div key={track} className="player">
          <span>{TRACK_LABELS[track]}</span>
          <audio
            controls
            preload="metadata"
            src={api.audioUrl(meetingId, track)}
            ref={(element) => {
              audioRefs.current[track] = element;
            }}
            data-testid={`audio-${track}`}
          />
        </div>
      ))}

      <BrainPanel
        meetingId={meetingId}
        onSeek={(segmentId) => {
          const segment = transcript.data?.segments.find((item) => item.id === segmentId);
          if (segment) {
            playFrom(segment);
            document.getElementById(`segment-${segment.id}`)?.scrollIntoView({ block: "center" });
          }
        }}
      />

      <h2>Transcript definitivo</h2>
      {transcript.data ? (
        <ol className="transcript">
          {transcript.data.segments.map((segment) => (
            <li
              key={segment.id}
              id={`segment-${segment.id}`}
              className={segment.id === activeSegment ? "active" : undefined}
            >
              <button type="button" className="segment" onClick={() => playFrom(segment)}>
                <span className="meta">
                  {formatTimestamp(segment.start)} · {TRACK_LABELS[segment.track]} ·{" "}
                  {segment.speaker ?? "Hablante no disponible"} · Idioma:{" "}
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
