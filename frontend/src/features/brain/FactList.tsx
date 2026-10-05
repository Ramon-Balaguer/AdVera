import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { type Fact } from "./factsApi";
import { sourceLink, sourceWhen } from "./links";

// A list of facts, each with its state, owner and date and the moments that support it. The
// citations open the meeting at the cited second (brain-global.md).
export function FactList({ facts, showMeeting }: { facts: Fact[]; showMeeting: boolean }) {
  const { t } = useTranslation();
  return (
    <ul className="fact-list">
      {facts.map((fact) => (
        <li key={fact.id} data-testid={`fact-${fact.kind}`}>
          <p>
            {fact.state && (
              <span className={`badge badge-${fact.state}`}>
                {t(`facts.state.${fact.state as "decided"}`, { defaultValue: fact.state })}
              </span>
            )}{" "}
            {fact.text}
          </p>
          <p className="meta">
            {fact.owner && <span>{t("facts.owner", { owner: fact.owner })} · </span>}
            {fact.due_date && <span>{t("facts.due", { date: fact.due_date })} · </span>}
            {showMeeting && (
              <>
                <Link to={`/meetings/${fact.meeting_id}`}>{fact.meeting_title}</Link>
                {fact.evidence.length > 0 && " · "}
              </>
            )}
            {fact.evidence.slice(0, 3).map((citation, index) => (
              <span key={citation.segment_id}>
                {index > 0 && " · "}
                <Link to={sourceLink({ meeting_id: fact.meeting_id, ...citation, start: citation.start ?? null })}>
                  {sourceWhen({ meeting_id: fact.meeting_id, ...citation, start: citation.start ?? null })}
                </Link>
              </span>
            ))}
          </p>
        </li>
      ))}
    </ul>
  );
}
