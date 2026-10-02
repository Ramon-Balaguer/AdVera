import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { fetchConceptDetail, relationLabel, typeLabel } from "./conceptGraphApi";
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
  const { t } = useTranslation();
  const detail = useQuery({
    queryKey: ["concept-detail", conceptId],
    queryFn: () => fetchConceptDetail(conceptId),
  });
  if (detail.isPending) return <aside className="inspector">{t("inspector.loading")}</aside>;
  if (detail.isError) return <aside className="inspector" role="alert">{t("inspector.loadError")}</aside>;
  const concept = detail.data;
  return (
    <aside className="inspector" data-testid="concept-inspector" aria-label={t("inspector.label", { label: concept.label })}>
      <div className="row">
        <h3 className="grow">{concept.label}</h3>
        <button type="button" onClick={onClose} aria-label={t("inspector.close")}>
          ✕
        </button>
      </div>
      <p className="meta">
        {typeLabel(concept.type)}
        {concept.aliases.length > 0 && t("inspector.alsoKnown", { aliases: concept.aliases.join(", ") })}
      </p>
      <p>
        <Link to={`/memory/timeline/${concept.id}`} data-testid="open-timeline">
          {t("inspector.timeline")}
        </Link>
      </p>

      <h4>{t("inspector.meetings")}</h4>
      <ul className="inspector-meetings">
        {concept.meetings.map((meeting) => (
          <li key={meeting.meeting_id}>
            <Link to={`/meetings/${meeting.meeting_id}`}>{meeting.title}</Link>
            {meeting.tagged && <span className="meta">{t("inspector.manualTag")}</span>}
            {meeting.spoke && <span className="meta">{t("inspector.speaks")}</span>}
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
          <h4>{t("inspector.relations")}</h4>
          <ul className="inspector-relations">
            {concept.relations.map((relation) => (
              <li key={relation.id}>
                {relation.direction === "outgoing" ? t("inspector.thisConcept") : "… "}
                {relationLabel(relation.type)}{" "}
                <button type="button" className="link" onClick={() => onSelect(relation.other_id)}>
                  {relation.other_label}
                </button>
                {relation.direction === "incoming" && t("inspector.toThisConcept")}
                {relation.source_type === "manual_user" && <span className="meta">{t("inspector.manual")}</span>}
                {relation.evidence.map((item) => (
                  <span key={`${relation.id}-${item.segment_id}`} className="meta">
                    {" "}
                    · {item.text ? `«${item.text}»` : t("inspector.segment", { id: item.segment_id })}
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
