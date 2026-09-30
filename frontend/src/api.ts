import { z } from "zod";

// Contracts mirror backend/app/meeting_contracts.py and backend/app/transcripts.py.
export const trackSchema = z.enum(["microphone", "system"]);
export type Track = z.infer<typeof trackSchema>;

export const meetingSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  status: z.enum(["scheduled", "recording", "processing", "ready", "failed", "archived"]),
  started_at: z.string().nullable(),
  ended_at: z.string().nullable(),
  duration: z.number().nullable(),
  primary_language: z.array(z.string()),
  created_by: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  attendee_count: z.number().nullable(),
  tracks: z.array(trackSchema),
});
export type Meeting = z.infer<typeof meetingSchema>;

export const transcriptionSchema = z.object({
  job_id: z.string(),
  meeting_id: z.string(),
  status: z.enum(["queued", "running", "completed", "failed"]),
  stage: z.string().nullable(),
  progress: z.number(),
  track: z.string().nullable(),
  processed_tracks: z.number(),
  total_tracks: z.number(),
  attempts: z.number(),
  max_attempts: z.number(),
  provider: z.string(),
  model: z.string(),
  error: z.string().nullable(),
  updated_at: z.string(),
});
export type Transcription = z.infer<typeof transcriptionSchema>;

export const segmentSchema = z.object({
  id: z.string(),
  start: z.number(),
  end: z.number(),
  text: z.string(),
  track: trackSchema,
  language: z.string().nullable(),
  speaker: z.string().nullable(),
});
export type Segment = z.infer<typeof segmentSchema>;

export const transcriptSchema = z.object({
  meeting_id: z.string(),
  status: z.literal("definitive"),
  primary_language: z.array(z.string()),
  segments: z.array(segmentSchema),
});
export type Transcript = z.infer<typeof transcriptSchema>;

export const importResponseSchema = z.object({
  meeting: meetingSchema,
  transcription: transcriptionSchema,
});

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw new ApiError(response.status, await errorCode(response));
  return schema.parse(await response.json());
}

async function errorCode(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : `HTTP_${response.status}`;
  } catch {
    return `HTTP_${response.status}`;
  }
}

const json = (body: unknown): RequestInit => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  listMeetings: () => request("/api/meetings", z.array(meetingSchema)),
  getMeeting: (id: string) => request(`/api/meetings/${id}`, meetingSchema),
  createMeeting: (title: string) =>
    request("/api/meetings", meetingSchema, { method: "POST", ...json({ title }) }),
  renameMeeting: (id: string, title: string) =>
    request(`/api/meetings/${id}`, meetingSchema, { method: "PATCH", ...json({ title }) }),
  deleteMeeting: async (id: string) => {
    const response = await fetch(`/api/meetings/${id}`, { method: "DELETE" });
    if (!response.ok) throw new ApiError(response.status, await errorCode(response));
  },
  getTranscription: async (id: string): Promise<Transcription | null> => {
    try {
      return await request(`/api/meetings/${id}/transcription`, transcriptionSchema);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  getTranscript: async (id: string): Promise<Transcript | null> => {
    try {
      return await request(`/api/meetings/${id}/transcript`, transcriptSchema);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  audioUrl: (id: string, track: Track) => `/api/meetings/${id}/audio/${track}`,
};

/** Upload with progress through XHR (fetch exposes no upload progress). */
export function uploadMedia(
  meetingId: string,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<z.infer<typeof importResponseSchema>> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/meetings/${meetingId}/imports`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiError(0, "NETWORK_ERROR"));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON error body */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(importResponseSchema.parse(body));
      } else {
        const detail = (body as { detail?: unknown } | null)?.detail;
        reject(new ApiError(xhr.status, typeof detail === "string" ? detail : `HTTP_${xhr.status}`));
      }
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

const ERROR_MESSAGES: Record<string, string> = {
  UNSUPPORTED_MEDIA: "Formato no soportado. Usa un archivo de audio o vídeo.",
  UPLOAD_TOO_LARGE: "El archivo supera el tamaño máximo permitido.",
  EMPTY_UPLOAD: "El archivo está vacío.",
  EXTRACTION_FAILED: "No se pudo extraer el audio del archivo.",
  EXTRACTION_TIMEOUT: "La extracción del audio tardó demasiado.",
  FFMPEG_UNAVAILABLE: "El servidor no tiene ffmpeg disponible.",
  MEETING_BUSY: "La reunión ya se está procesando.",
  IMPORT_IN_PROGRESS: "Ya hay una importación en curso para esta reunión.",
  ASR_FAILED: "La transcripción definitiva falló. El audio se conserva.",
  EMPTY_TRANSCRIPT: "No se detectó habla en el audio.",
  NO_AUDIO: "La reunión no tiene audio almacenado.",
  INPUT_CHANGED: "El audio cambió mientras se procesaba.",
  LEASE_EXPIRED: "El proceso de transcripción se interrumpió.",
  INTERNAL_ERROR: "Error interno durante la transcripción.",
  NETWORK_ERROR: "No se pudo contactar con el servidor.",
};

export function describeError(code: string | null | undefined): string {
  if (!code) return "Error desconocido.";
  return ERROR_MESSAGES[code] ?? `Error (${code}).`;
}
