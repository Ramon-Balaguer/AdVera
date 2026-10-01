import { z } from "zod";

// Contracts mirror backend/app/meeting_contracts.py and backend/app/transcripts.py.
export const trackSchema = z.enum(["microphone", "system"]);
export type Track = z.infer<typeof trackSchema>;

export const tagSchema = z.object({
  assignment_id: z.string(),
  concept_id: z.string(),
  label: z.string(),
  created_at: z.string().nullable().optional(),
});
export type Tag = z.infer<typeof tagSchema>;

export const tagSummarySchema = z.object({
  concept_id: z.string(),
  label: z.string(),
  meetings: z.number(),
});
export type TagSummary = z.infer<typeof tagSummarySchema>;

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
  tags: z.array(tagSchema).default([]),
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
  person: z.string().nullable().optional(), // the person the speaker was named as (ADR 0021)
});
export type Segment = z.infer<typeof segmentSchema>;

const analysisSchema = z.enum(["queued", "waiting_transcript", "llm_not_configured", "unchanged"]);
export const notesSchema = z.object({
  meeting_id: z.string(),
  content: z.string(),
  updated_at: z.string().nullable(),
  analysis: analysisSchema.nullable().optional(),
});
export type Notes = z.infer<typeof notesSchema>;
export const backlinkSchema = z.object({
  meeting_id: z.string(),
  title: z.string(),
  segment_id: z.string().nullable(),
  note_block_id: z.string(),
});
export const personSchema = z.object({ concept_id: z.string(), name: z.string(), meetings: z.number() });
export type Person = z.infer<typeof personSchema>;
export const speakerSchema = z.object({
  track: z.string(),
  speaker: z.string(),
  seconds: z.number(),
  segments: z.number(),
  sample: z.string(),
  person: z.string().nullable(),
  concept_id: z.string().nullable(),
});
export type MeetingSpeaker = z.infer<typeof speakerSchema>;
const speakersSchema = z.object({ speakers: z.array(speakerSchema), analysis: analysisSchema.nullable().optional() });

export const transcriptSchema = z.object({
  meeting_id: z.string(),
  status: z.literal("definitive"),
  primary_language: z.array(z.string()),
  segments: z.array(segmentSchema),
});
export type Transcript = z.infer<typeof transcriptSchema>;

export const audioMetricsSchema = z.object({
  session_id: z.string(),
  capture_session_id: z.string().nullable().optional(),
  status: z.enum(["recording", "stopped"]),
  next_sequence: z.number(),
  tracks: z.record(z.string(), z.object({ frames: z.number(), bytes: z.number(), duration: z.number() })),
});
export type AudioMetrics = z.infer<typeof audioMetricsSchema>;

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
  createMeeting: (title: string, tags: string[] = []) =>
    request("/api/meetings", meetingSchema, { method: "POST", ...json({ title, tags }) }),
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
  getAudioMetrics: async (id: string): Promise<AudioMetrics | null> => {
    try {
      return await request(`/api/meetings/${id}/audio-metrics`, audioMetricsSchema);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  audioUrl: (id: string, track: Track) => `/api/meetings/${id}/audio/${track}`,
  listTags: () => request("/api/meetings/tags", z.array(tagSummarySchema)),
  tagSuggestions: (id: string, q: string) =>
    request(`/api/meetings/${id}/tags/suggestions?q=${encodeURIComponent(q)}`, z.array(tagSummarySchema)),
  addTag: (id: string, label: string) =>
    request(`/api/meetings/${id}/tags`, tagSchema, { method: "POST", ...json({ label }) }),
  removeTag: async (id: string, assignmentId: string) => {
    const response = await fetch(`/api/meetings/${id}/tags/${assignmentId}`, { method: "DELETE" });
    if (!response.ok) throw new ApiError(response.status, await errorCode(response));
  },
  getNotes: (id: string) => request(`/api/meetings/${id}/notes`, notesSchema),
  saveNotes: (id: string, content: string) =>
    request(`/api/meetings/${id}/notes`, notesSchema, { method: "PUT", ...json({ content }) }),
  getBacklinks: (id: string) => request(`/api/meetings/${id}/references`, z.array(backlinkSchema)),
  listPeople: () => request("/api/people", z.array(personSchema)),
  getSpeakers: (id: string) => request(`/api/meetings/${id}/speakers`, speakersSchema),
  saveSpeakers: (id: string, assignments: { track: string; speaker: string; person: string | null }[]) =>
    request(`/api/meetings/${id}/speakers`, speakersSchema, { method: "PUT", ...json({ assignments }) }),
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
  MEETING_BUSY: "La reunión ya se está procesando, grabando o importando.",
  MEETING_ALREADY_RECORDED: "Esta reunión ya tiene audio grabado. Crea otra reunión para grabar de nuevo.",
  IMPORT_IN_PROGRESS: "Ya hay una importación en curso para esta reunión.",
  FILE_TOO_LARGE: "El archivo supera el tamaño máximo permitido.",
  LENGTH_REQUIRED: "No se pudo determinar el tamaño del archivo.",
  ASR_FAILED: "La transcripción definitiva falló. El audio se conserva.",
  EMPTY_TRANSCRIPT: "No se detectó habla en el audio.",
  NO_AUDIO: "La reunión no tiene audio almacenado.",
  INPUT_CHANGED: "El audio cambió mientras se procesaba.",
  LEASE_EXPIRED: "El proceso de transcripción se interrumpió.",
  INTERNAL_ERROR: "Error interno durante la transcripción.",
  NETWORK_ERROR: "No se pudo contactar con el servidor.",
  MICROPHONE_UNAVAILABLE: "No se pudo acceder al micrófono. Revisa los permisos del navegador.",
  STALE_CURSOR: "La sesión de grabación ya avanzó en otra conexión.",
  OLLAMA_UNREACHABLE: "No se pudo conectar con el servidor Ollama.",
  OLLAMA_HTTP_ERROR: "El servidor Ollama respondió con un error.",
  OLLAMA_INVALID_RESPONSE: "La respuesta no parece de un servidor Ollama.",
  INVALID_URL: "La URL no es válida.",
  UNKNOWN_SPEAKER: "Ese hablante ya no está en la transcripción.",
  INVALID_PERSON: "El nombre no es válido: no puede estar vacío ni pasar de 100 caracteres.",
  INVALID_TAG: "La etiqueta no es válida: no puede estar vacía ni pasar de 60 caracteres.",
  TOO_MANY_TAGS: "Esta reunión ya tiene el máximo de 20 etiquetas.",
  TAG_NOT_FOUND: "Esa etiqueta ya no está en la reunión.",
  UNSAFE_DESTINATION: "Esa dirección no está permitida para el servidor de modelos.",
  UNRESOLVABLE_HOST: "No se pudo resolver el nombre del servidor.",
  AGENT_UNAVAILABLE: "El agente de escritorio no está conectado.",
  CAPTURE_ADAPTER_UNAVAILABLE: "El agente no puede abrir alguna de las pistas de audio.",
  CAPTURE_ALREADY_ACTIVE: "El agente ya está grabando otra sesión.",
  CAPTURE_START_TIMEOUT: "El agente no respondió a tiempo.",
  CAPTURE_FAILED: "El agente no pudo iniciar la captura.",
  AGENT_DISCONNECTED: "Se perdió la conexión con el agente durante la grabación. Puedes finalizarla con el audio ya guardado.",
  TRACK_SEND_FAILED: "El agente perdió la conexión de una pista y detuvo la captura.",
  CAPTURE_LIMIT_REACHED: "La grabación alcanzó la duración máxima permitida.",
  MEDIA_TOO_LONG: "El archivo dura más de lo permitido.",
  STORAGE_ERROR: "El servidor no pudo guardar el audio (¿disco lleno?). La grabación se detuvo.",
  INVALID_FRAME: "El backend rechazó un fragmento de audio.",
  SESSION_NOT_ACTIVE: "La sesión de grabación ya no está activa.",
  INVALID_COMMAND: "El backend no entendió una orden de grabación.",
  CONSENT_DENIED: "Quien está en el equipo con el agente no permitió la grabación.",
  CONSENT_UNAVAILABLE:
    "El agente no puede pedir confirmación en su equipo. Ejecútalo con la bandeja o con --allow-remote-recording.",
  AGENT_CAPTURE_ACTIVE: "El agente está grabando esta reunión.",
  SESSION_NOT_RECOVERABLE: "La sesión de grabación ya no se puede recuperar.",
};

export function describeError(code: string | null | undefined): string {
  if (!code) return "Error desconocido.";
  return ERROR_MESSAGES[code] ?? `Error (${code}).`;
}
