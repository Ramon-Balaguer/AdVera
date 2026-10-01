import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { z } from "zod";

import { ApiError, describeError } from "../../api";
import { formatTimestamp } from "../../format";

// Brain panel (brain-extraction-from-definitive-transcript.md): Decisions first, every item
// cites definitive transcript segments that open the audio at the right second.
const evidenceSchema = z.object({
  segment_id: z.string(),
  start: z.number().nullable(), // a note block has no time (ADR 0020)
  end: z.number().nullable(),
  speaker: z.string().nullable().optional(),
  track: z.string().nullable().optional(),
});
const itemSchema = z.object({
  text: z.string(),
  evidence: z.array(evidenceSchema),
  state: z.string().optional(),
  owner: z.string().nullable().optional(),
  due_date: z.string().nullable().optional(),
});
type BrainItem = z.infer<typeof itemSchema>;
const brainSchema = z.object({
  meeting_id: z.string(),
  state: z.enum(["blocked", "not_started", "queued", "running", "completed", "empty", "failed"]),
  llm_configured: z.boolean(),
  job: z
    .object({ status: z.string(), model: z.string(), language: z.string(), error: z.string().nullable(), attempts: z.number() })
    .nullable()
    .optional(),
  result: z
    .object({
      summary: z.object({ text: z.string(), evidence: z.array(evidenceSchema) }),
      decisions: z.array(itemSchema),
      actions: z.array(itemSchema),
      topics: z.array(itemSchema),
      open_questions: z.array(itemSchema),
      risks: z.array(itemSchema),
      // Items the model produced without a valid citation are never stored; only their count is.
      dropped_items: z.number().optional(),
    })
    .nullable()
    .optional(),
});
type Brain = z.infer<typeof brainSchema>;

const DECISION_STATES: Record<string, string> = {
  decided: "Decidida",
  proposed: "Propuesta",
  rejected: "Rechazada",
  superseded: "Sustituida",
  unknown: "Sin confirmar",
};

const ERRORS: Record<string, string> = {
  LLM_NOT_CONFIGURED: "No hay modelo configurado.",
  LLM_UNAVAILABLE: "No se pudo contactar con el servidor LLM.",
  LLM_MODEL_NOT_FOUND: "El modelo configurado no existe en el servidor.",
  LLM_INVALID_JSON: "El modelo devolvió una respuesta no válida.",
  BRAIN_SCHEMA_INVALID: "El modelo devolvió una estructura no válida.",
  TRANSCRIPT_TOO_LONG: "El transcript supera el contexto configurado del modelo.",
  INPUT_CHANGED: "El transcript cambió; genera el Brain de nuevo.",
};

async function fetchBrain(meetingId: string): Promise<Brain> {
  const response = await fetch(`/api/meetings/${meetingId}/brain`);
  if (!response.ok) throw new ApiError(response.status, `HTTP_${response.status}`);
  return brainSchema.parse(await response.json());
}

async function regenerate(meetingId: string): Promise<void> {
  const response = await fetch(`/api/meetings/${meetingId}/brain`, { method: "POST" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : "HTTP_ERROR");
  }
}

/** "note-003" -> "Apuntes ¶3": how a cited note block is shown. */
export function noteLabel(blockId: string) {
  return `Apuntes ¶${Number(blockId.replace(/^note-/, "")) || blockId}`;
}

function Citations({ item, onSeek }: { item: Pick<BrainItem, "evidence">; onSeek: (segmentId: string) => void }) {
  return (
    <span className="citations">
      {item.evidence.map((evidence) => (
        <button
          key={evidence.segment_id}
          type="button"
          className="citation"
          onClick={() => onSeek(evidence.segment_id)}
          title={evidence.track === "notes" ? "Ir a este apunte" : `Ir al segmento ${evidence.segment_id}`}
        >
          {evidence.track === "notes" || evidence.start === null
            ? noteLabel(evidence.segment_id)
            : formatTimestamp(evidence.start)}
        </button>
      ))}
    </span>
  );
}

function Section({ title, items, onSeek }: { title: string; items: BrainItem[]; onSeek: (id: string) => void }) {
  if (items.length === 0) return null;
  return (
    <div className="brain-section">
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => (
          <li key={index}>
            {item.state && <span className={`badge badge-${item.state}`}>{DECISION_STATES[item.state] ?? item.state}</span>}
            <span>{item.text}</span>
            {item.owner && <span className="meta"> · {item.owner}</span>}
            {item.due_date && <span className="meta"> · {item.due_date}</span>}
            <Citations item={item} onSeek={onSeek} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BrainPanel({ meetingId, onSeek }: { meetingId: string; onSeek: (segmentId: string) => void }) {
  const queryClient = useQueryClient();
  const brain = useQuery({
    queryKey: ["brain", meetingId],
    queryFn: () => fetchBrain(meetingId),
    refetchInterval: (query) =>
      query.state.data?.state === "queued" || query.state.data?.state === "running" ? 3000 : false,
  });
  const generate = useMutation({
    mutationFn: () => regenerate(meetingId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["brain", meetingId] }),
  });

  const data = brain.data;
  if (!data) return null;
  const result = data.result;
  const busy = data.state === "queued" || data.state === "running";
  const canGenerate = data.llm_configured && !busy && data.state !== "blocked";

  return (
    <section className="brain" aria-label="Brain de la reunión">
      <div className="row brain-header">
        <h2>Brain</h2>
        {data.state !== "blocked" && (
          <button type="button" disabled={!canGenerate || generate.isPending} onClick={() => generate.mutate()}>
            {data.state === "not_started" ? "Generar Brain" : data.state === "failed" ? "Reintentar" : "Regenerar"}
          </button>
        )}
        {data.job && <span className="meta">{data.job.model}</span>}
      </div>

      {data.state === "blocked" && <p className="hint">Disponible cuando exista el transcript definitivo.</p>}
      {!data.llm_configured && data.state !== "blocked" && (
        <p className="hint">
          Configura el servidor y el modelo LLM en <Link to="/settings">Ajustes</Link> para generar el Brain.
        </p>
      )}
      {busy && (
        <p role="status" aria-live="polite" data-testid="brain-status">
          {data.state === "queued" ? "Brain en cola…" : "Analizando el transcript definitivo…"}
        </p>
      )}
      {data.state === "failed" && (
        <p role="alert">
          El Brain falló: {ERRORS[data.job?.error ?? ""] ?? describeError(data.job?.error)}
        </p>
      )}
      {generate.isError && (
        <p role="alert">{ERRORS[(generate.error as ApiError).code] ?? describeError((generate.error as ApiError).code)}</p>
      )}
      {data.state === "empty" && (
        <p data-testid="brain-empty">
          {result?.dropped_items
            ? `El modelo produjo ${result.dropped_items} elemento(s), pero ninguno tenía una cita válida del transcript, así que no se guardó ninguno.`
            : "El modelo no encontró decisiones, tareas ni temas en este transcript."}
        </p>
      )}

      {result && data.state === "completed" && (
        <div data-testid="brain-result">
          <Section title="Decisiones" items={result.decisions} onSeek={onSeek} />
          {result.summary.text && (
            <div className="brain-section">
              <h3>Resumen</h3>
              <p>
                {result.summary.text} <Citations item={result.summary} onSeek={onSeek} />
              </p>
            </div>
          )}
          <Section title="Acciones" items={result.actions} onSeek={onSeek} />
          <Section title="Temas" items={result.topics} onSeek={onSeek} />
          <Section title="Preguntas abiertas" items={result.open_questions} onSeek={onSeek} />
          <Section title="Riesgos" items={result.risks} onSeek={onSeek} />
          {result.dropped_items ? (
            <p className="hint" data-testid="brain-dropped">
              {result.dropped_items} elemento(s) del modelo se descartaron por no tener una cita válida.
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
