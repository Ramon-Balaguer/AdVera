import { z } from "zod";

import { ApiError } from "../../api";
import { LANGUAGES } from "../../i18n";

// What Settings and the first-start wizard share: the settings shape, the request helper and
// the check of a model server (ADR 0023, ADR 0025).
export const settingsSchema = z.object({
  llm_provider: z.string(),
  llm_base_url: z.string(),
  llm_model: z.string(),
  llm_output_language: z.enum(LANGUAGES),
  llm_api_key_set: z.boolean().default(false),
  llm_configured: z.boolean(),
  setup_completed: z.boolean().default(false),
  setup_required: z.boolean().default(false),
});
export type RuntimeSettings = z.infer<typeof settingsSchema>;

// The providers the backend can talk to (ADR 0023).
export const PROVIDERS = ["ollama", "openai"] as const;
export type Provider = (typeof PROVIDERS)[number];
export const isProvider = (value: string): value is Provider => (PROVIDERS as readonly string[]).includes(value);

export async function jsonRequest<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `HTTP_${response.status}`);
  return schema.parse(body);
}

export const loadSettings = () => jsonRequest("/api/settings", settingsSchema);

// `llm_api_key` is only ever sent, never read back: an empty string removes the stored one.
export const saveSettings = (body: Partial<RuntimeSettings> & { llm_api_key?: string }) =>
  jsonRequest("/api/settings", settingsSchema, { method: "PUT", body: JSON.stringify(body) });

export const discoverModels = ({ provider, baseUrl, apiKey }: { provider: Provider; baseUrl: string; apiKey?: string }) =>
  jsonRequest("/api/settings/models", z.object({ base_url: z.string(), models: z.array(z.string()) }), {
    method: "POST",
    // Without a typed key the server checks with the stored one.
    body: JSON.stringify({ provider, base_url: baseUrl, ...(apiKey ? { api_key: apiKey } : {}) }),
  });
