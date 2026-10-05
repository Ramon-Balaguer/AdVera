import type { UseMutationResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, describeError } from "../../api";
import { PROVIDERS, type Provider } from "./settingsApi";

type Discovery = UseMutationResult<{ base_url: string; models: string[] }, Error, { provider: Provider; baseUrl: string }>;

// The provider, the server address and the check of the server: the same controls in
// Settings and in the first-start wizard.
export function ServerFields({
  provider,
  onProvider,
  url,
  onUrl,
  models,
  idPrefix = "llm",
}: {
  provider: Provider;
  onProvider: (provider: Provider) => void;
  url: string;
  onUrl: (url: string) => void;
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
          onProvider(event.target.value as Provider);
          models.reset(); // the list belongs to the other provider
        }}
      >
        {PROVIDERS.map((name) => (
          <option key={name} value={name}>
            {t(`settings.providers.${name}`)}
          </option>
        ))}
      </select>
      {provider === "openai" && <p className="hint">{t("settings.providerHint")}</p>}

      <label htmlFor={`${idPrefix}-url`}>{t("settings.url")}</label>
      <div className="row">
        <input
          id={`${idPrefix}-url`}
          className="grow"
          value={url}
          onChange={(event) => onUrl(event.target.value)}
          placeholder={t(`settings.urlPlaceholder.${provider}`)}
        />
        <button type="button" onClick={() => models.mutate({ provider, baseUrl: url })} disabled={!url || models.isPending}>
          {models.isPending ? t("settings.checking") : t("settings.check")}
        </button>
      </div>
      <div role="status" aria-live="polite" className="hint">
        {models.isSuccess && t("settings.connected", { count: models.data.models.length })}
      </div>
      {models.isError && <p role="alert">{describeError(models.error instanceof ApiError ? models.error.code : null)}</p>}
    </>
  );
}
