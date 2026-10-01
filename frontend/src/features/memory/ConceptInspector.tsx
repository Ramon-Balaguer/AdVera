import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchConceptDetail, RELATION_LABELS, TYPE_LABELS } from "./conceptGraphApi";
import { sourceLink, sourceWhen } from "./links";

// What the graph knows about one concept, with the moments that support it. Transcript
// evidence opens the meeting at that second; a manual tag says it has none.
export function ConceptInspector({
  conceptId,
  onSelect,
  onClose,
}: {
  conceptId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const detail = useQuery({
    queryKey: ["concept-detail", conceptId],
    queryFn: () => fetchConceptDetail(conceptId),
  });
  if (detail.isPending) return <aside className="inspector">Cargando…</aside>;
  if (detail.isError) return <aside className="inspector" role="alert">No se pudo cargar el concepto.</aside>;
  const concept = detail.data;
  return (
    <aside className="inspector" data-testid="concept-inspector" aria-label={`Concepto ${concept.label}`}>
      <div className="row">
        <h3 className="grow">{concept.label}</h3>
        <button type="button" onClick={onClose} aria-label="Cerrar el inspector">
          ✕
        </button>
      </div>
      <p className="meta">
        {TYPE_LABELS[concept.type] ?? concept.type}
        {concept.aliases.length > 0 && ` · también: ${concept.aliases.join(", ")}`}
      </p>
      <p>
        <Link to={`/memory/timeline/${concept.id}`} data-testid="open-timeline">
          Ver su línea de tiempo
        </Link>
      </p>

      <h4>Reuniones</h4>
      <ul className="inspector-meetings">
        {concept.meetings.map((meeting) => (
          <li key={meeting.meeting_id}>
            <Link to={`/meetings/${meeting.meeting_id}`}>{meeting.title}</Link>
            {meeting.tagged && <span className="meta"> · etiqueta manual (sin evidencia del transcript)</span>}
            {meeting.spoke && <span className="meta"> · habla en esta reunión</span>}
            {meeting.evidence.length > 0 && (
              <ol className="sources">
                {meeting.evidence.map((item) => (
                  <li key={item.segment_id}>
                    <Link to={sourceLink({ meeting_id: meeting.meeting_id, ...item })}>
                      {sourceWhen({ meeting_id: meeting.meeting_id, ...item })}
                    </Link>
                    {item.text && <blockquote>{item.text}</blockquote>}
                  </li>
                ))}
              </ol>
            )}
          </li>
        ))}
      </ul>

      {concept.relations.length > 0 && (
        <>
          <h4>Relaciones</h4>
          <ul className="inspector-relations">
            {concept.relations.map((relation) => (
              <li key={relation.id}>
                {relation.direction === "outgoing" ? "Este concepto " : "… "}
                {RELATION_LABELS[relation.type] ?? relation.type}{" "}
                <button type="button" className="link" onClick={() => onSelect(relation.other_id)}>
                  {relation.other_label}
                </button>
                {relation.direction === "incoming" && " → este concepto"}
                {relation.source_type === "manual_user" && <span className="meta"> · manual</span>}
                {relation.evidence.map((item) => (
                  <span key={`${relation.id}-${item.segment_id}`} className="meta">
                    {" "}
                    · {item.text ? `«${item.text}»` : `segmento ${item.segment_id}`}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
