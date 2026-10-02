import i18n from "./i18n";
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

export function describeError(code: string | null | undefined): string {
  if (!code) return i18n.t("common.unknownError");
  const key = `errors.${code}`;
  return i18n.exists(key) ? i18n.t(key as "errors.NO_AUDIO") : i18n.t("common.errorCode", { code });
}
