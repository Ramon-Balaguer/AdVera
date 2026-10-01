import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useState } from "react";

import { api, ApiError, describeError, type MeetingSpeaker, type Person } from "../../api";
import { formatTimestamp } from "../../format";
import { tagKey } from "../tags/TagPicker";

const ANALYSIS: Record<string, string> = {
  queued: "Guardado. Brain volverá a analizar la reunión con estos nombres.",
  waiting_transcript: "Guardado.",
  llm_not_configured: "Guardado. Configura el LLM en Ajustes para analizarlo.",
  unchanged: "Guardado.",
};

const TRACKS: Record<string, string> = { microphone: "Micrófono", system: "Sistema" };
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
        placeholder="Nombre de la persona"
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
        <ul className="tag-suggestions" role="listbox" id={listId} aria-label="Personas conocidas">
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
      setStatus(ANALYSIS[result.analysis ?? "unchanged"] ?? "Guardado.");
      void queryClient.invalidateQueries({ queryKey: ["transcript", meetingId] });
      void queryClient.invalidateQueries({ queryKey: ["people"] });
      void queryClient.invalidateQueries({ queryKey: ["brain", meetingId] });
      void queryClient.invalidateQueries({ queryKey: ["concept-graph"] });
    } catch (failure) {
      setError(describeError(failure instanceof ApiError ? failure.code : null));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="speakers" aria-label="Hablantes">
      <div className="row">
        <h2>Hablantes</h2>
        <button type="button" onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? "Guardando…" : "Guardar"}
        </button>
      </div>
      <table className="speakers-table">
        <thead>
          <tr>
            <th>Hablante</th>
            <th>Tiempo</th>
            <th>Persona</th>
          </tr>
        </thead>
        <tbody>
          {list.map((speaker) => (
            <tr key={key(speaker)}>
              <td>
                {speaker.speaker} <span className="meta">· {TRACKS[speaker.track] ?? speaker.track}</span>
                <div className="meta sample">«{speaker.sample}…»</div>
              </td>
              <td>
                {formatTimestamp(speaker.seconds)} <span className="meta">({speaker.segments})</span>
              </td>
              <td>
                <PersonInput
                  label={`Persona de ${speaker.speaker} (${TRACKS[speaker.track] ?? speaker.track})`}
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
