import { type KeyboardEvent, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { TagSummary } from "../../api";

const MAX_LENGTH = 60;

// The same comparison as the server's canonical key: case, accents and spacing do not matter.
export function tagKey(text: string) {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

// Choose several tags while typing: existing tags are offered as you type (most used first),
// so the same tag is reused instead of written again in another spelling (ADR 0013). With
// `allowNew` a typed text that matches no tag is added as a new one (Enter); without it only
// existing tags can be chosen, which is what a filter needs.
export function TagPicker({
  value,
  onChange,
  options,
  allowNew,
  label,
  placeholder,
  max = 20,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  options: TagSummary[];
  allowNew: boolean;
  label: string;
  placeholder: string;
  max?: number;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const listId = useId();
  const chosen = useMemo(() => new Set(value.map(tagKey)), [value]);

  const typed = tagKey(text);
  const suggestions = useMemo(() => {
    if (!typed) return [];
    return options
      .filter((option) => !chosen.has(tagKey(option.label)) && tagKey(option.label).includes(typed))
      .sort(
        (a, b) =>
          Number(tagKey(b.label).startsWith(typed)) - Number(tagKey(a.label).startsWith(typed)) ||
          b.meetings - a.meetings ||
          a.label.localeCompare(b.label),
      )
      .slice(0, 8);
  }, [options, chosen, typed]);
  const shown = open && suggestions.length > 0;

  const add = (raw: string) => {
    const tag = raw.replace(/\s+/g, " ").trim();
    if (!tagKey(tag)) return;
    if (tag.length > MAX_LENGTH) return setError(t("tags.tooLong", { max: MAX_LENGTH }));
    if (chosen.has(tagKey(tag))) return setText("");
    if (value.length >= max) return setError(t("tags.tooMany", { max }));
    onChange([...value, tag]);
    setText("");
    setActive(0);
    setError(null);
  };

  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && suggestions.length) {
      event.preventDefault();
      setOpen(true);
      setActive((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp" && suggestions.length) {
      event.preventDefault();
      setActive((index) => (index - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter" || (event.key === "," && allowNew)) {
      if (!typed) return;
      event.preventDefault(); // never submits the surrounding form while choosing a tag
      const exact = options.find((option) => tagKey(option.label) === typed);
      if (shown) add(suggestions[active].label);
      else if (exact) add(exact.label);
      else if (allowNew) add(text);
      else setError(t("tags.doesNotExist"));
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "Backspace" && !text && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="tag-picker">
      <ul className="chips" aria-label={t("tags.chosen", { label })}>
        {value.map((tag) => (
          <li key={tagKey(tag)} className="chip">
            <span>{tag}</span>
            <button type="button" aria-label={t("tags.remove", { label: tag })} onClick={() => onChange(value.filter((t) => t !== tag))}>
              ✕
            </button>
          </li>
        ))}
        <li className="tag-picker-input">
          <input
            role="combobox"
            aria-label={label}
            aria-expanded={shown}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={shown ? `${listId}-${active}` : undefined}
            value={text}
            placeholder={value.length ? "" : placeholder}
            autoComplete="off"
            maxLength={MAX_LENGTH + 20}
            onChange={(event) => {
              setText(event.target.value);
              setOpen(true);
              setActive(0);
              setError(null);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={keyDown}
          />
        </li>
      </ul>
      {shown && (
        <ul className="tag-suggestions" role="listbox" id={listId} aria-label={t("tags.existing")}>
          {suggestions.map((option, index) => (
            <li
              key={option.concept_id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              // mousedown, not click: it runs before the input loses focus and closes the list
              onMouseDown={(event) => {
                event.preventDefault();
                add(option.label);
              }}
            >
              {option.label} <span className="meta">({option.meetings})</span>
            </li>
          ))}
        </ul>
      )}
      {allowNew && typed && !shown && open && (
        <p className="hint">{t("tags.pressEnter", { label: text.trim() })}</p>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
