import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { TagPicker } from "../tags/TagPicker";
import { FactList } from "./FactList";
import { DECISION_STATES, FACT_KINDS, type FactKind, fetchFacts } from "./factsApi";

// Decisions, actions, open questions, risks and topics of all the meetings (ADR 0024). Read
// only; the filters run on the server and every row opens its meeting at the cited second.
const PAGE = 50;

export function FactsPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const meetingId = params.get("meeting") ?? "";
  const [kind, setKind] = useState<FactKind>("decision");
  const [state, setState] = useState("");
  const [owner, setOwner] = useState("");
  const [text, setText] = useState("");
  const [typed, setTyped] = useState({ q: "", owner: "" });
  const [tags, setTags] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const tagOptions = useQuery({ queryKey: ["tags"], queryFn: api.listTags });

  useEffect(() => {
    const timer = window.setTimeout(() => setTyped({ q: text.trim(), owner: owner.trim() }), 300);
    return () => window.clearTimeout(timer);
  }, [text, owner]);
  // A new filter starts again from the first page.
  useEffect(() => setLimit(PAGE), [kind, state, typed, tags, dateFrom, dateTo, meetingId]);

  const facts = useQuery({
    queryKey: ["facts", kind, state, typed, tags, dateFrom, dateTo, limit, meetingId],
    queryFn: () => fetchFacts({ kind, state, owner: typed.owner, q: typed.q, tags, dateFrom, dateTo, limit, meetingId }),
    placeholderData: keepPreviousData,
  });

  return (
    <section className="facts-page">
      <p>
        <Link to="/brain">{t("facts.back")}</Link>
      </p>
      <h1>{t("facts.title")}</h1>
      {meetingId && (
        <p className="hint" data-testid="facts-one-meeting">
          {t("facts.oneMeeting")}{" "}
          <button type="button" onClick={() => setParams({}, { replace: true })}>
            {t("facts.allMeetings")}
          </button>
        </p>
      )}
      <div className="tabs" role="tablist" aria-label={t("facts.kinds")}>
        {FACT_KINDS.map((item) => (
          <button
            key={item}
            role="tab"
            type="button"
            aria-selected={kind === item}
            className={kind === item ? "active" : ""}
            onClick={() => setKind(item)}
          >
            {t(`facts.kind.${item}`)} {facts.data ? `(${facts.data.counts[item] ?? 0})` : ""}
          </button>
        ))}
      </div>

      <div className="row">
        <label className="grow">
          <span className="visually-hidden">{t("facts.search")}</span>
          <input value={text} placeholder={t("facts.searchPlaceholder")} onChange={(event) => setText(event.target.value)} />
        </label>
        {kind === "decision" && (
          <label>
            {t("facts.stateFilter")}{" "}
            <select value={state} onChange={(event) => setState(event.target.value)}>
              <option value="">{t("common.all")}</option>
              {DECISION_STATES.map((item) => (
                <option key={item} value={item}>
                  {t(`facts.state.${item}`)}
                </option>
              ))}
            </select>
          </label>
        )}
        {kind === "action" && (
          <label>
            <span className="visually-hidden">{t("facts.ownerFilter")}</span>
            <input value={owner} placeholder={t("facts.ownerPlaceholder")} onChange={(event) => setOwner(event.target.value)} />
          </label>
        )}
        <label>
          {t("facts.from")} <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </label>
        <label>
          {t("facts.to")} <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </label>
      </div>
      <TagPicker
        value={tags}
        onChange={setTags}
        options={tagOptions.data ?? []}
        allowNew={false}
        label={t("facts.filterTags")}
        placeholder={t("facts.tagsPlaceholder")}
      />

      {facts.isError && <p role="alert">{t("facts.loadError")}</p>}
      {facts.data &&
        (facts.data.facts.length === 0 ? (
          <p data-testid="facts-empty">{t("facts.empty")}</p>
        ) : (
          <>
            <p className="meta" data-testid="facts-total">
              {t("facts.total", { count: facts.data.total })}
            </p>
            <FactList facts={facts.data.facts} showMeeting />
            {facts.data.total > facts.data.facts.length && (
              <button type="button" onClick={() => setLimit((current) => current + PAGE)}>
                {t("facts.more")}
              </button>
            )}
          </>
        ))}
    </section>
  );
}
