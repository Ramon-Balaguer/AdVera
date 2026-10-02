import i18n, { locale } from "./i18n";

export function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

const STATUSES = ["scheduled", "recording", "processing", "ready", "failed", "archived"] as const;
const TRACKS = ["microphone", "system", "notes"] as const;

export function statusLabel(status: string): string {
  return (STATUSES as readonly string[]).includes(status)
    ? i18n.t(`status.${status as (typeof STATUSES)[number]}`)
    : status;
}

export function trackLabel(track: string): string {
  return (TRACKS as readonly string[]).includes(track) ? i18n.t(`track.${track as (typeof TRACKS)[number]}`) : track;
}

/** A date in the current language ("15 January 2026"). */
export function formatDate(value: string | Date, style: "long" | "medium" = "long"): string {
  return new Intl.DateTimeFormat(locale(), { dateStyle: style }).format(new Date(value));
}
