import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, ApiError, describeError, type Tag } from "../../api";

const MAX_LENGTH = 60;

// Manual tags (ADR 0013): free text, shared across meetings. Existing tags are suggested while
// typing so the same tag is reused instead of typed again in another spelling.
export function MeetingTags({ meetingId, tags }: { meetingId: string; tags: Tag[] }) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const [label, setLabel] = useState("");
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setTyped(label.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [label]);

  const suggestions = useQuery({
    queryKey: ["tag-suggestions", meetingId, typed, tags.length],
    queryFn: () => api.tagSuggestions(meetingId, typed),
    enabled: typed.length > 0,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
    void queryClient.invalidateQueries({ queryKey: ["meetings"] });
    void queryClient.invalidateQueries({ queryKey: ["tags"] });
    void queryClient.invalidateQueries({ queryKey: ["concept-graph"] });
  };
  const add = useMutation({
    mutationFn: (value: string) => api.addTag(meetingId, value),
    onSuccess: (_created, submitted) => {
      // A slow answer must not wipe what the user has typed since.
      setLabel((current) => (current.trim() === submitted ? "" : current));
      setError(null);
      refresh();
    },
    onError: (failure) => setError(describeError(failure instanceof ApiError ? failure.code : null)),
  });
  const remove = useMutation({
    mutationFn: (assignmentId: string) => api.removeTag(meetingId, assignmentId),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (failure) => {
      setError(describeError(failure instanceof ApiError ? failure.code : null));
      refresh(); // the tag may already be gone: show what is really there
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = label.trim();
    if (!value) return;
    if (value.length > MAX_LENGTH) {
      setError(describeError("INVALID_TAG"));
      return;
    }
    add.mutate(value);
  };

  return (
    <section className="tags" aria-label={t("tags.region")}>
      <h2 className="visually-hidden">{t("tags.heading")}</h2>
      {tags.length === 0 ? (
        <p className="hint">{t("tags.none")}</p>
      ) : (
        <ul className="chips" data-testid="meeting-tags">
          {tags.map((tag) => (
            <li key={tag.assignment_id} className="chip">
              <Link to={`/memory/timeline/${tag.concept_id}`} title={t("tags.timelineOf", { label: tag.label })}>
                {tag.label}
              </Link>
              <button
                type="button"
                aria-label={t("tags.remove", { label: tag.label })}
                disabled={remove.isPending}
                onClick={() => remove.mutate(tag.assignment_id)}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="row" onSubmit={submit}>
        <label className="grow">
          <span className="visually-hidden">{t("tags.add")}</span>
          <input
            value={label}
            maxLength={MAX_LENGTH + 20}
            placeholder={t("tags.add")}
            autoComplete="off"
            onChange={(event) => setLabel(event.target.value)}
          />
        </label>
        <button type="submit" disabled={!label.trim() || add.isPending}>
          {t("tags.addButton")}
        </button>
      </form>
      {typed && (suggestions.data?.length ?? 0) > 0 && (
        <ul className="chips suggestions" aria-label={t("tags.existing")}>
          {suggestions.data!.map((item) => (
            <li key={item.concept_id}>
              <button
                type="button"
                onClick={() => {
                  setLabel(""); // choosing a suggestion replaces what was being typed
                  setTyped("");
                  add.mutate(item.label);
                }}
                disabled={add.isPending}
              >
                {item.label} ({item.meetings})
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
