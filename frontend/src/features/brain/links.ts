import { formatTimestamp } from "../../format";
import i18n from "../../i18n";

interface Cited {
  meeting_id: string;
  start: number | null;
  segment_id: string;
  track?: string | null;
}

const isNote = (source: Cited) => source.track === "notes" || source.segment_id.startsWith("note-");

// A source opens its meeting at the cited second and starts playing (brain-global.md);
// a cited note block (ADR 0020) opens the meeting's notes at that block.
export function sourceLink(source: Cited) {
  if (isNote(source)) return `/meetings/${source.meeting_id}?note=${encodeURIComponent(source.segment_id)}`;
  return `/meetings/${source.meeting_id}?at=${Math.floor(source.start ?? 0)}&segment=${encodeURIComponent(source.segment_id)}&play=1`;
}

/** How a citation is labelled: the second it was said, or "Notes ¶3" for a note block. */
export function sourceWhen(source: Cited) {
  if (isNote(source)) {
    return i18n.t("notes.paragraph", { n: Number(source.segment_id.replace(/^note-/, "")) || source.segment_id });
  }
  return formatTimestamp(source.start ?? 0);
}
