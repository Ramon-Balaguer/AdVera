import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError, describeError, type MeetingSpeaker, type Person } from "../../api";
import { formatTimestamp, trackLabel } from "../../format";
import i18n from "../../i18n";
import { tagKey } from "../tags/TagPicker";

const analysisMessage = (analysis: string | null | undefined) =>
  analysis === "queued"
    ? i18n.t("analysis.speakersQueued")
    : analysis === "llm_not_configured"
      ? i18n.t("analysis.llm_not_configured")
      : i18n.t("analysis.unchanged");

const key = (speaker: MeetingSpeaker) => `${speaker.track}|${speaker.speaker}`;

// One name per speaker, with the people already known offered while typing (ADR 0021).
function PersonInput({
  label,
  value,
  onChange,
  people,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  people: Person[];
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const typed = tagKey(value);
  const offered = useMemo(
    () =>
      typed
        ? people
            .filter((p) => tagKey(p.name).includes(typed) && tagKey(p.name) !== typed)
            .sort(
              (a, b) =>
                Number(tagKey(b.name).startsWith(typed)) - Number(tagKey(a.name).startsWith(typed)) ||
                b.meetings - a.meetings,
            )
            .slice(0, 6)
        : [],
    [people, typed],
  );
  const shown = open && offered.length > 0;
  return (
    <div className="person-input">
      <input
        role="combobox"
        aria-label={label}
        aria-expanded={shown}
        aria-controls={listId}
        aria-autocomplete="list"
        value={value}
        maxLength={100}
        placeholder={t("speakers.personPlaceholder")}
        autoComplete="off"
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (!shown) return;
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((index) => (index + 1) % offered.length);
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((index) => (index - 1 + offered.length) % offered.length);
          } else if (event.key === "Enter") {
            event.preventDefault();
            onChange(offered[active].name);
            setOpen(false);
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {shown && (
        <ul className="tag-suggestions" role="listbox" id={listId} aria-label={t("speakers.known")}>
          {offered.map((person, index) => (
            <li
              key={person.concept_id}
              role="option"
              aria-selected={index === active}
              onMouseDown={(event) => {
                event.preventDefault();
                onChange(person.name);
                setOpen(false);
              }}
            >
              {person.name} <span className="meta">({person.meetings})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MeetingSpeakers({ meetingId, hasTranscript }: { meetingId: string; hasTranscript: boolean }) {
  const queryClient = useQueryClient();
  const speakers = useQuery({
    queryKey: ["speakers", meetingId],
    queryFn: () => api.getSpeakers(meetingId),
    enabled: hasTranscript,
  });
  const people = useQuery({ queryKey: ["people"], queryFn: api.listPeople, enabled: hasTranscript });
  const { t } = useTranslation();
  const [names, setNames] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (speakers.data) setNames(Object.fromEntries(speakers.data.speakers.map((s) => [key(s), s.person ?? ""])));
  }, [speakers.data]);

  if (!hasTranscript || !speakers.data || speakers.data.speakers.length === 0) return null;
  const list = speakers.data.speakers;
  const dirty = list.some((s) => (names[key(s)] ?? "").trim() !== (s.person ?? ""));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveSpeakers(
        meetingId,
        list.map((s) => ({ track: s.track, speaker: s.speaker, person: (names[key(s)] ?? "").trim() || null })),
      );
      queryClient.setQueryData(["speakers", meetingId], result);
      setStatus(analysisMessage(result.analysis));
      void queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
      void queryClient.invalidateQueries({ queryKey: ["people"] });
      void queryClient.invalidateQueries({ queryKey: ["summary", meetingId] });
      void queryClient.invalidateQueries({ queryKey: ["concept-graph"] });
    } catch (failure) {
      setError(describeError(failure instanceof ApiError ? failure.code : null));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="speakers" aria-label={t("speakers.title")}>
      <div className="row">
        <h2>{t("speakers.title")}</h2>
        <button type="button" onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
      <table className="speakers-table">
        <thead>
          <tr>
            <th>{t("speakers.colSpeaker")}</th>
            <th>{t("speakers.colTime")}</th>
            <th>{t("speakers.colPerson")}</th>
          </tr>
        </thead>
        <tbody>
          {list.map((speaker) => (
            <tr key={key(speaker)}>
              <td>
                {speaker.speaker} <span className="meta">· {trackLabel(speaker.track)}</span>
                <div className="meta sample">«{speaker.sample}…»</div>
              </td>
              <td>
                {formatTimestamp(speaker.seconds)} <span className="meta">({speaker.segments})</span>
              </td>
              <td>
                <PersonInput
                  label={t("speakers.personOf", { speaker: speaker.speaker, track: trackLabel(speaker.track) })}
                  value={names[key(speaker)] ?? ""}
                  onChange={(next) => {
                    setNames((current) => ({ ...current, [key(speaker)]: next }));
                    setStatus(null);
                  }}
                  people={people.data ?? []}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {status && !dirty && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
