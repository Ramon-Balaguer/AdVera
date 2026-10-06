import type { UseMutationResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, describeError } from "../../api";
import { FIXED_URLS, OPENAI_PRESETS, PROVIDERS, type Provider, isHosted } from "./settingsApi";

type Discovery = UseMutationResult<{ base_url: string; models: string[] }, Error, { provider: Provider; baseUrl: string; apiKey?: string }>;

// The provider, the server address and the check of the server: the same controls in
// Settings and in the first-start wizard.
export function ServerFields({
  provider,
  onProvider,
  url,
  onUrl,
  apiKey,
  onApiKey,
  keySet = false,
  onRemoveKey,
  models,
  idPrefix = "llm",
}: {
  provider: Provider;
  onProvider: (provider: Provider) => void;
  url: string;
  onUrl: (url: string) => void;
  apiKey: string;
  onApiKey: (key: string) => void;
  keySet?: boolean; // a key is already stored on the server
  onRemoveKey?: () => void;
  models: Discovery;
  idPrefix?: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      <label htmlFor={`${idPrefix}-provider`}>{t("settings.provider")}</label>
      <select
        id={`${idPrefix}-provider`}
        value={provider}
        onChange={(event) => {
          const next = event.target.value as Provider;
          onProvider(next);
          const fixed = FIXED_URLS[next];
          if (fixed) onUrl(fixed); // the hosted services have one address
          models.reset(); // the list belongs to the other provider
        }}
      >
        {PROVIDERS.map((name) => (
          <option key={name} value={name}>
            {t(`settings.providers.${name}`)}
          </option>
        ))}
      </select>
      {provider === "openai" && (
        <>
          <p className="hint">{t("settings.providerHint")}</p>
          <label htmlFor={`${idPrefix}-preset`}>{t("settings.preset")}</label>
          <select
            id={`${idPrefix}-preset`}
            value={Object.entries(OPENAI_PRESETS).find(([, u]) => u === url)?.[0] ?? "custom"}
            onChange={(event) => {
              const preset = OPENAI_PRESETS[event.target.value as keyof typeof OPENAI_PRESETS];
              if (preset) onUrl(preset);
              models.reset();
            }}
          >
            <option value="custom">{t("settings.presets.custom")}</option>
            {Object.keys(OPENAI_PRESETS).map((name) => (
              <option key={name} value={name}>
                {t(`settings.presets.${name as keyof typeof OPENAI_PRESETS}`)}
              </option>
            ))}
          </select>
        </>
      )}

      <label htmlFor={`${idPrefix}-url`}>{t("settings.url")}</label>
      <div className="row">
        <input
          id={`${idPrefix}-url`}
          className="grow"
          value={url}
          onChange={(event) => onUrl(event.target.value)}
          placeholder={t(`settings.urlPlaceholder.${provider}`)}
        />
        <button type="button" onClick={() => models.mutate({ provider, baseUrl: url, apiKey })} disabled={!url || models.isPending}>
          {models.isPending ? t("settings.checking") : t("settings.check")}
        </button>
      </div>

      {isHosted(provider, url) && <p className="notice">{t("settings.hostedNotice")}</p>}

      <label htmlFor={`${idPrefix}-api-key`}>{t("settings.apiKey")}</label>
      <div className="row">
        <input
          id={`${idPrefix}-api-key`}
          className="grow"
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(event) => onApiKey(event.target.value)}
          placeholder={keySet ? t("settings.apiKeyStored") : t("settings.apiKeyPlaceholder")}
        />
        {keySet && onRemoveKey && (
          <button type="button" onClick={onRemoveKey}>
            {t("settings.apiKeyRemove")}
          </button>
        )}
      </div>
      <div role="status" aria-live="polite" className="hint">
        {models.isSuccess && t("settings.connected", { count: models.data.models.length })}
      </div>
      {models.isError && <p role="alert">{describeError(models.error instanceof ApiError ? models.error.code : null)}</p>}
    </>
  );
}
