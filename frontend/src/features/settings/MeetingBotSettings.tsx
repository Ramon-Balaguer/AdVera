import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { describeError } from "../../api";
import { type RuntimeSettings, saveSettings } from "./settingsApi";

/**
 * Meeting bot settings (ADR 0026): where the self-hosted Vexa is, its API key, the webhook
 * secret and the bot's name. The key and the secret are never read back: blank keeps them.
 */
export function MeetingBotSettings({ settings }: { settings: RuntimeSettings }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState(settings.vexa_base_url);
  const [name, setName] = useState(settings.vexa_bot_name);
  const [speakerNames, setSpeakerNames] = useState(settings.vexa_speaker_names);
  const [leaveMinutes, setLeaveMinutes] = useState(settings.vexa_leave_alone_seconds / 60);
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setUrl(settings.vexa_base_url);
    setName(settings.vexa_bot_name);
    setSpeakerNames(settings.vexa_speaker_names);
    setLeaveMinutes(settings.vexa_leave_alone_seconds / 60);
  }, [settings.vexa_base_url, settings.vexa_bot_name, settings.vexa_speaker_names, settings.vexa_leave_alone_seconds]);

  const save = useMutation({
    mutationFn: saveSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      void queryClient.invalidateQueries({ queryKey: ["meeting-bot-capabilities"] });
      setApiKey("");
      setSecret("");
      setSaved(true);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    save.mutate({
      vexa_base_url: url.trim(),
      vexa_bot_name: name,
      vexa_speaker_names: speakerNames,
      vexa_leave_alone_seconds: Math.round(leaveMinutes * 60),
      ...(apiKey ? { vexa_api_key: apiKey } : {}),
      ...(secret ? { vexa_webhook_secret: secret } : {}),
    });
  };
  const webhookUrl = `${window.location.origin}/api/integrations/vexa/webhook`;

  return (
    <form className="settings" onSubmit={submit} aria-label={t("settings.bot.legend")}>
      <fieldset>
        <legend>{t("settings.bot.legend")}</legend>
        <p className="hint">{t("settings.bot.hint")}</p>

        <label htmlFor="vexa-url">{t("settings.bot.url")}</label>
        <input
          id="vexa-url"
          type="url"
          value={url}
          placeholder={t("settings.bot.urlPlaceholder")}
          onChange={(event) => setUrl(event.target.value)}
        />

        <label htmlFor="vexa-key">{t("settings.bot.apiKey")}</label>
        <input
          id="vexa-key"
          type="password"
          autoComplete="off"
          value={apiKey}
          placeholder={settings.vexa_api_key_set ? t("settings.bot.stored") : ""}
          onChange={(event) => setApiKey(event.target.value)}
        />

        <label htmlFor="vexa-secret">{t("settings.bot.webhookSecret")}</label>
        <input
          id="vexa-secret"
          type="password"
          autoComplete="off"
          value={secret}
          placeholder={settings.vexa_webhook_secret_set ? t("settings.bot.stored") : ""}
          onChange={(event) => setSecret(event.target.value)}
        />
        <p className="hint">{t("settings.bot.webhookHint", { url: webhookUrl })}</p>

        <label htmlFor="vexa-name">{t("settings.bot.name")}</label>
        <input id="vexa-name" value={name} maxLength={100} required onChange={(event) => setName(event.target.value)} />

        <label htmlFor="vexa-leave">{t("settings.bot.leaveAlone")}</label>
        <input
          id="vexa-leave"
          type="number"
          min={0.5}
          max={60}
          step={0.5}
          required
          value={leaveMinutes}
          onChange={(event) => setLeaveMinutes(Number(event.target.value))}
        />
        <p className="hint">{t("settings.bot.leaveAloneHint")}</p>

        <label className="checkbox">
          <input type="checkbox" checked={speakerNames} onChange={(event) => setSpeakerNames(event.target.checked)} />{" "}
          {t("settings.bot.speakerNames")}
        </label>

        <button type="submit" disabled={save.isPending}>
          {t("settings.bot.save")}
        </button>
        {saved && <p role="status">{t("settings.bot.saved")}</p>}
        {save.error && <p role="alert">{describeError(save.error.message)}</p>}
      </fieldset>
    </form>
  );
}
