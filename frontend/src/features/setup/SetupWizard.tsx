import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Logo } from "../../Logo";
import { type Language, LANGUAGES, setLanguage as applyInterfaceLanguage } from "../../i18n";
import { ServerFields } from "../settings/ServerFields";
import { type Provider, discoverModels, saveSettings } from "../settings/settingsApi";

// The first start (ADR 0025): the minimum to begin, the same choices as Settings. It takes the
// place of the application until a model is chosen or the wizard is skipped, and everything it
// sets can be changed later in Settings.
const STEPS = ["language", "server", "model", "done"] as const;
type Step = (typeof STEPS)[number];

// Each language is offered in its own name, whatever the current one.
const LANGUAGE_NAMES: Record<Language, string> = { en: "English", es: "Español", ca: "Català" };

export function SetupWizard() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("language");
  const [language, setLanguage] = useState<Language>(
    (LANGUAGES as readonly string[]).includes(i18n.language) ? (i18n.language as Language) : "en",
  );
  const [provider, setProvider] = useState<Provider>("ollama");
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");
  const models = useMutation({ mutationFn: discoverModels });

  const finish = useMutation({
    mutationFn: (skip: boolean) =>
      saveSettings(
        skip
          ? { llm_output_language: language, setup_completed: true }
          : {
              llm_provider: provider,
              llm_base_url: url,
              llm_model: model,
              llm_output_language: language,
              setup_completed: true,
            },
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      queryClient.setQueryData(["interface-language"], { llm_output_language: data.llm_output_language, setup_required: false });
      applyInterfaceLanguage(data.llm_output_language);
      navigate("/meetings", { replace: true });
    },
  });

  const index = STEPS.indexOf(step);
  const available = models.data?.models ?? [];
  const checked = models.isSuccess;
  const canNext = step === "language" || (step === "server" && checked) || (step === "model" && model !== "") || step === "done";

  const chooseLanguage = (next: Language) => {
    setLanguage(next);
    applyInterfaceLanguage(next); // the rest of the wizard already speaks it
  };

  return (
    <main className="setup" aria-label={t("setup.title")}>
      <div className="setup-card">
        <div className="brand">
          <Logo size={32} />
          <span className="brand-name">AdVera</span>
        </div>
        <h1>{t("setup.title")}</h1>
        <p className="meta" data-testid="setup-step">
          {t("setup.step", { current: index + 1, total: STEPS.length })} · {t(`setup.steps.${step}`)}
        </p>

        {step === "language" && (
          <fieldset>
            <legend>{t("setup.languageQuestion")}</legend>
            <p className="hint">{t("setup.languageHint")}</p>
            {LANGUAGES.map((code) => (
              <label key={code} className="setup-choice">
                <input type="radio" name="language" checked={language === code} onChange={() => chooseLanguage(code)} />{" "}
                {LANGUAGE_NAMES[code]}
              </label>
            ))}
          </fieldset>
        )}

        {step === "server" && (
          <fieldset>
            <legend>{t("setup.serverQuestion")}</legend>
            <p className="hint">{t("setup.serverHint")}</p>
            <ServerFields
              provider={provider}
              onProvider={(next) => {
                setProvider(next);
                setModel("");
              }}
              url={url}
              onUrl={(next) => {
                setUrl(next);
                setModel("");
              }}
              models={models}
              idPrefix="setup"
            />
          </fieldset>
        )}

        {step === "model" && (
          <fieldset>
            <legend>{t("setup.modelQuestion")}</legend>
            <p className="hint">{t("setup.modelHint")}</p>
            <label htmlFor="setup-model">{t("settings.model")}</label>
            <select id="setup-model" value={model} onChange={(event) => setModel(event.target.value)}>
              <option value="">{t("settings.chooseModel")}</option>
              {available.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </fieldset>
        )}

        {step === "done" && (
          <div data-testid="setup-summary">
            <h2>{t("setup.summaryTitle")}</h2>
            <dl className="system-facts">
              <dt>{t("setup.steps.language")}</dt>
              <dd>{LANGUAGE_NAMES[language]}</dd>
              <dt>{t("settings.provider")}</dt>
              <dd>{t(`settings.providers.${provider}`)}</dd>
              <dt>{t("settings.url")}</dt>
              <dd>{url}</dd>
              <dt>{t("settings.model")}</dt>
              <dd>{model}</dd>
            </dl>
          </div>
        )}

        <p className="notice" data-testid="setup-change-later">
          {t("setup.changeLater")}
        </p>
        {finish.isError && <p role="alert">{t("settings.saveError")}</p>}

        <div className="row setup-actions">
          <button type="button" onClick={() => finish.mutate(true)} disabled={finish.isPending}>
            {t("setup.skip")}
          </button>
          <span className="grow" />
          {index > 0 && (
            <button type="button" onClick={() => setStep(STEPS[index - 1])} disabled={finish.isPending}>
              {t("setup.back")}
            </button>
          )}
          {step !== "done" ? (
            <button type="button" className="primary" onClick={() => setStep(STEPS[index + 1])} disabled={!canNext}>
              {t("setup.next")}
            </button>
          ) : (
            <button type="button" className="primary" onClick={() => finish.mutate(false)} disabled={finish.isPending}>
              {t("setup.start")}
            </button>
          )}
        </div>
      </div>
    </main>
  );
}
