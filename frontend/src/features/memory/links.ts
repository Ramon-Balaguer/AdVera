// A source opens its meeting at the cited second and starts playing (brain-memoria-global.md).
export function sourceLink(source: { meeting_id: string; start: number; segment_id: string }) {
  return `/meetings/${source.meeting_id}?at=${Math.floor(source.start)}&segment=${encodeURIComponent(source.segment_id)}&play=1`;
}
