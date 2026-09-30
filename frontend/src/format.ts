export function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export const STATUS_LABELS: Record<string, string> = {
  scheduled: "Programada",
  recording: "Grabando",
  processing: "Procesando",
  ready: "Lista",
  failed: "Fallida",
  archived: "Archivada",
};

export const TRACK_LABELS: Record<string, string> = {
  microphone: "Micrófono",
  system: "Sistema",
};
