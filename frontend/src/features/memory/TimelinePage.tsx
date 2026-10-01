import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "../../api";
import { TYPE_LABELS } from "./conceptGraphApi";
import { sourceLink, sourceWhen } from "./links";

// How a concept or tag evolved across meetings, oldest first, with the moments that cite it
// (rebuild-concept-timeline.md). Read-only.
const citationSchema = z.object({
  segment_id: z.string(),
  start: z.number().nullable(),
  track: z.string().nullable().optional(),
  text: z.string().nullable().optional(),
});
const factSchema = z.object({
  kind: z.enum(["decision", "action", "risk", "question", "topic"]),
  text: z.string(),
  state: z.string().nullable().optional(),
  owner: z.string().nullable().optional(),
  due_date: z.string().nullable().optional(),
  evidence: z.array(citationSchema),
});
const timelineSchema = z.object({
  concept_id: z.string(),
  label: z.string(),
  type: z.string(),
  is_tag: z.boolean(),
  truncated: z.boolean(),
  entries: z.array(
    z.object({
      meeting_id: z.string(),
      title: z.string(),
      date: z.string(),
      mentioned: z.boolean(),
      tagged: z.boolean(),
      spoke: z.boolean(),
      quotes: z.array(citationSchema),
      facts: z.array(factSchema),
      summary: z.string().nullable().optional(),
    }),
  ),
});
type Citation = z.infer<typeof citationSchema>;

const KIND_LABELS: Record<string, string> = {
  decision: "Decisión",
  action: "Acción",
  risk: "Riesgo",
  question: "Pregunta",
  topic: "Tema",
};

async function fetchTimeline(id: string) {
  const response = await fetch(`/api/memory/concepts/${id}/timeline`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `HTTP_${response.status}`);
  }
  return timelineSchema.parse(await response.json());
}

function Cite({ meetingId, citation }: { meetingId: string; citation: Citation }) {
  const source = { meeting_id: meetingId, ...citation, start: citation.start ?? null };
  return (
    <Link className="citation" to={sourceLink(source)} title={citation.text ?? undefined}>
      {sourceWhen(source)}
    </Link>
  );
}

const DATE = new Intl.DateTimeFormat("es-ES", { dateStyle: "long" });

export function TimelinePage() {
  const { conceptId = "" } = useParams();
  const timeline = useQuery({ queryKey: ["timeline", conceptId], queryFn: () => fetchTimeline(conceptId), retry: 1 });

  if (timeline.isPending) return <p role="status">Cargando la línea de tiempo…</p>;
  if (timeline.isError) {
    const missing = timeline.error instanceof ApiError && timeline.error.status === 404;
    return <p role="alert">{missing ? "Ese concepto ya no aparece en ninguna reunión." : "No se pudo cargar la línea de tiempo."}</p>;
  }
  const data = timeline.data;
  return (
    <section className="timeline-page">
      <p>
        <Link to="/memory">← Memoria</Link>
      </p>
      <h1>
        Línea de tiempo: {data.label}{" "}
        <span className="meta">{data.is_tag ? "etiqueta" : (TYPE_LABELS[data.type] ?? data.type)}</span>
      </h1>
      <p className="meta">
        {data.entries.length === 1 ? "1 reunión" : `${data.entries.length} reuniones`}, de la más antigua a la más reciente
        {data.truncated && " (solo las más recientes)"}.
      </p>
      <ol className="timeline" data-testid="timeline">
        {data.entries.map((entry) => (
          <li key={entry.meeting_id} className="timeline-entry">
            <div className="timeline-date">{DATE.format(new Date(entry.date))}</div>
            <div className="timeline-body">
              <h2>
                <Link to={`/meetings/${entry.meeting_id}`}>{entry.title}</Link>
              </h2>
              <p className="meta">
                {[entry.mentioned && "mencionado", entry.tagged && "etiquetada", entry.spoke && "habla en la reunión"]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {entry.summary && <p className="timeline-summary">{entry.summary}</p>}
              {entry.facts.length > 0 && (
                <ul className="timeline-facts">
                  {entry.facts.map((fact, index) => (
                    <li key={`${fact.kind}-${index}`}>
                      <span className={`badge badge-${fact.kind}`}>{KIND_LABELS[fact.kind]}</span> {fact.text}
                      {fact.owner && <span className="meta"> · {fact.owner}</span>}
                      {fact.due_date && <span className="meta"> · {fact.due_date}</span>}{" "}
                      {fact.evidence.map((citation) => (
                        <Cite key={citation.segment_id} meetingId={entry.meeting_id} citation={citation} />
                      ))}
                    </li>
                  ))}
                </ul>
              )}
              {entry.quotes.length > 0 && (
                <ul className="timeline-quotes">
                  {entry.quotes.map((quote) => (
                    <li key={quote.segment_id}>
                      <Cite meetingId={entry.meeting_id} citation={quote} />
                      {quote.text && <blockquote>{quote.text}</blockquote>}
                    </li>
                  ))}
                </ul>
              )}
              {entry.facts.length === 0 && entry.quotes.length === 0 && !entry.summary && (
                <p className="meta">Sin hechos ni citas en esta reunión.</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
