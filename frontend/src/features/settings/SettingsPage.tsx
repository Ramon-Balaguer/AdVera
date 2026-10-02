import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { ApiError, describeError } from "../../api";
import { type Language, LANGUAGES, setLanguage as applyInterfaceLanguage } from "../../i18n";

// Each language is offered in its own name, whatever the current one.
const LANGUAGE_NAMES: Record<Language, string> = { en: "English", es: "Español", ca: "Català" };

// Settings (persistent-runtime-settings.md, ollama-connectivity-model-selection.md, ADR 0009).
const settingsSchema = z.object({
  llm_provider: z.string(),
  llm_base_url: z.string(),
  llm_model: z.string(),
  llm_output_language: z.enum(LANGUAGES),
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
  const { t } = useTranslation();
  const settings = useQuery({ queryKey: ["settings"], queryFn: loadSettings });
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");
  const [language, setLanguage] = useState<Language>("en");
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
      // The interface follows the saved language at once.
      queryClient.setQueryData(["interface-language"], { llm_output_language: data.llm_output_language });
      applyInterfaceLanguage(data.llm_output_language);
      setSaved(true);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    save.mutate({ llm_base_url: url, llm_model: model, llm_output_language: language });
  };

  if (settings.isPending) return <p>{t("settings.loading")}</p>;
  if (settings.isError) return <p role="alert">{t("settings.loadError")}</p>;

  const available = models.data?.models ?? [];
  const options = model && !available.includes(model) ? [model, ...available] : available;

  return (
    <section>
      <h1>{t("settings.title")}</h1>
      <form className="settings" onSubmit={submit}>
        <fieldset>
          <legend>{t("settings.llm")}</legend>
          <label htmlFor="llm-url">{t("settings.url")}</label>
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
              {models.isPending ? t("settings.checking") : t("settings.check")}
            </button>
          </div>
          <div role="status" aria-live="polite" className="hint">
            {models.isSuccess && t("settings.connected", { count: available.length })}
          </div>
          {models.isError && (
            <p role="alert">{describeError(models.error instanceof ApiError ? models.error.code : null)}</p>
          )}

          <label htmlFor="llm-model">{t("settings.model")}</label>
          <select id="llm-model" value={model} onChange={(event) => setModel(event.target.value)}>
            <option value="">{t("settings.chooseModel")}</option>
            {options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>

          <label htmlFor="llm-language">{t("settings.language")}</label>
          <select
            id="llm-language"
            value={language}
            onChange={(event) => setLanguage(event.target.value as Language)}
          >
            {LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {LANGUAGE_NAMES[code]}
              </option>
            ))}
          </select>

          <p className="notice">
            {t("settings.notice")}
          </p>
        </fieldset>

        <div className="row">
          <button type="submit" disabled={save.isPending || !url}>
            {t("common.save")}
          </button>
          {saved && <span role="status">{t("settings.saved")}</span>}
          {save.isError && <span role="alert">{t("settings.saveError")}</span>}
        </div>
      </form>
    </section>
  );
}
