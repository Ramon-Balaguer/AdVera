import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../../api";

// Meetings whose notes reference this one with @ (ADR 0020).
export function MeetingBacklinks({ meetingId }: { meetingId: string }) {
  const { t } = useTranslation();
  const backlinks = useQuery({ queryKey: ["backlinks", meetingId], queryFn: () => api.getBacklinks(meetingId) });
  if (!backlinks.data?.length) return null;
  return (
    <section className="backlinks" aria-label={t("backlinks.title")}>
      <h2>{t("backlinks.title")}</h2>
      <ul>
        {backlinks.data.map((link) => (
          <li key={`${link.meeting_id}-${link.note_block_id}-${link.segment_id ?? ""}`}>
            <Link to={`/meetings/${link.meeting_id}?note=${link.note_block_id}`}>{link.title}</Link>
            {link.segment_id && <span className="meta">{t("backlinks.moment")}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
