import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { z } from "zod";

import { ApiError, describeError } from "../../api";

// Settings (persistent-runtime-settings.md, ollama-connectivity-model-selection.md, ADR 0009).
const settingsSchema = z.object({
  llm_provider: z.string(),
  llm_base_url: z.string(),
  llm_model: z.string(),
  llm_output_language: z.enum(["es", "en"]),
  llm_configured: z.boolean(),
});
type RuntimeSettings = z.infer<typeof settingsSchema>;

async function jsonRequest<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `HTTP_${response.status}`);
  return schema.parse(body);
}

const loadSettings = () => jsonRequest("/api/settings", settingsSchema);
const discoverModels = (baseUrl: string) =>
  jsonRequest("/api/settings/ollama/models", z.object({ base_url: z.string(), models: z.array(z.string()) }), {
    method: "POST",
    body: JSON.stringify({ base_url: baseUrl }),
  });

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: loadSettings });
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");
  const [language, setLanguage] = useState<"es" | "en">("es");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    setUrl(settings.data.llm_base_url);
    setModel(settings.data.llm_model);
    setLanguage(settings.data.llm_output_language);
  }, [settings.data]);

  const models = useMutation({ mutationFn: discoverModels });
  // ollama-settings-auto-discovery.md: load the model list once the stored URL is known.
  const storedUrl = settings.data?.llm_base_url;
  useEffect(() => {
    if (storedUrl) models.mutate(storedUrl);
  }, [storedUrl]);

  const save = useMutation({
    mutationFn: (body: Partial<RuntimeSettings>) =>
      jsonRequest("/api/settings", settingsSchema, { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      setSaved(true);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    save.mutate({ llm_base_url: url, llm_model: model, llm_output_language: language });
  };

  if (settings.isPending) return <p>Cargando ajustes…</p>;
  if (settings.isError) return <p role="alert">No se pudieron cargar los ajustes.</p>;

  const available = models.data?.models ?? [];
  const options = model && !available.includes(model) ? [model, ...available] : available;

  return (
    <section>
      <h1>Ajustes</h1>
      <form className="settings" onSubmit={submit}>
        <fieldset>
          <legend>Modelo de lenguaje (Ollama)</legend>
          <label htmlFor="llm-url">URL del servidor Ollama</label>
          <div className="row">
            <input
              id="llm-url"
              className="grow"
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
                setSaved(false);
              }}
              placeholder="https://ollama.example.com"
            />
            <button type="button" onClick={() => models.mutate(url)} disabled={!url || models.isPending}>
              {models.isPending ? "Comprobando…" : "Comprobar"}
            </button>
          </div>
          <div role="status" aria-live="polite" className="hint">
            {models.isSuccess && `Conectado: ${available.length} modelos disponibles.`}
          </div>
          {models.isError && (
            <p role="alert">{describeError(models.error instanceof ApiError ? models.error.code : null)}</p>
          )}

          <label htmlFor="llm-model">Modelo</label>
          <select id="llm-model" value={model} onChange={(event) => setModel(event.target.value)}>
            <option value="">— Selecciona un modelo —</option>
            {options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>

          <label htmlFor="llm-language">Idioma de las respuestas del Brain</label>
          <select
            id="llm-language"
            value={language}
            onChange={(event) => setLanguage(event.target.value as "es" | "en")}
          >
            <option value="es">Español</option>
            <option value="en">English</option>
          </select>

          <p className="notice">
            El contenido de los transcripts se envía a este servidor para generar el Brain y responder
            preguntas. Usa solo servidores de confianza.
          </p>
        </fieldset>

        <div className="row">
          <button type="submit" disabled={save.isPending || !url}>
            Guardar
          </button>
          {saved && <span role="status">Ajustes guardados.</span>}
          {save.isError && <span role="alert">No se pudieron guardar los ajustes: revisa la URL.</span>}
        </div>
      </form>
    </section>
  );
}
