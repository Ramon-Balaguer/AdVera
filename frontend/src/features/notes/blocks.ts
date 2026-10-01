// The same block split and @reference format as backend/app/notes.py (ADR 0020): blocks are
// separated by blank lines, a heading alone joins the block after it, ids are note-001…
export const REFERENCE =
  /\[@([^\]\n]{1,200})\]\(\/meetings\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\?segment=([A-Za-z0-9_-]{1,50}))?\)/g;

const HEADING = /^\s{0,3}#{1,6}\s/;

export interface NoteBlockRange {
  id: string;
  from: number;
  to: number;
}

export function noteBlocks(markdown: string): NoteBlockRange[] {
  const paragraphs: { from: number; to: number; text: string }[] = [];
  const separator = /\n\s*\n/g;
  let start = 0;
  let match: RegExpExecArray | null;
  const push = (from: number, to: number) => {
    const raw = markdown.slice(from, to);
    const lead = raw.length - raw.trimStart().length;
    const text = raw.trim();
    if (text) paragraphs.push({ from: from + lead, to: from + lead + text.length, text });
  };
  while ((match = separator.exec(markdown))) {
    push(start, match.index);
    start = match.index + match[0].length;
  }
  push(start, markdown.length);

  const merged: { from: number; to: number }[] = [];
  let pending: { from: number; to: number } | null = null;
  for (const paragraph of paragraphs) {
    if (paragraph.text.split("\n").every((line) => HEADING.test(line))) {
      pending = pending ? { from: pending.from, to: paragraph.to } : { from: paragraph.from, to: paragraph.to };
      continue;
    }
    merged.push(pending ? { from: pending.from, to: paragraph.to } : { from: paragraph.from, to: paragraph.to });
    pending = null;
  }
  if (pending) merged.push(pending);
  return merged.map((range, index) => ({ id: `note-${String(index + 1).padStart(3, "0")}`, ...range }));
}

export function referenceMarkdown(label: string, meetingId: string, segmentId?: string) {
  const clean = label.replace(/[[\]\n]/g, " ").replace(/\s+/g, " ").trim().slice(0, 200) || "reunión";
  return `[@${clean}](/meetings/${meetingId}${segmentId ? `?segment=${segmentId}` : ""})`;
}
