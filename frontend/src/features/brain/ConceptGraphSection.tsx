import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api";
import { ConceptGraph } from "./ConceptGraph";
import { ConceptInspector } from "./ConceptInspector";
import { CONCEPT_TYPES, fetchConceptGraph, typeLabel } from "./conceptGraphApi";

// The concept graph of all meetings, read-only (concept-graph.md). Filters run on the server.
// Concepts without any relationship are left out by default so the view stays readable as
// meetings accumulate; a search always includes them, so a loose concept can still be found.
export function ConceptGraphSection({ meetingId = "" }: { meetingId?: string }) {
  const { t } = useTranslation();
  const [type, setType] = useState("");
  const [text, setText] = useState("");
  const [typed, setTyped] = useState("");
  const [tag, setTag] = useState("");
  const [showIsolated, setShowIsolated] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.listTags });

  const includeIsolated = showIsolated || typed !== "";

  // New filters draw another graph: an inspector left open would describe a node not shown.
  useEffect(() => setSelected(null), [type, typed, tag, includeIsolated]);

  useEffect(() => {
    const timer = window.setTimeout(() => setTyped(text.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [text]);

  const graph = useQuery({
    queryKey: ["concept-graph", type, typed, tag, includeIsolated, meetingId],
    queryFn: () => fetchConceptGraph({ type, q: typed, tag, includeIsolated, meetingId }),
    retry: 1,
    refetchInterval: (query) => (query.state.data?.state === "partial" ? 10_000 : false),
  });

  return (
    <section className="concept-section" aria-label={t("graph.title")}>
      <h2>{t("graph.title")}</h2>
      <div className="row">
        <label>
          {t("graph.type")}{" "}
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="">{t("common.allMasc")}</option>
            {CONCEPT_TYPES.map((item) => (
              <option key={item} value={item}>
                {typeLabel(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          <span className="visually-hidden">{t("graph.search")}</span>
          <input value={text} placeholder={t("graph.searchPlaceholder")} onChange={(event) => setText(event.target.value)} />
        </label>
        {(tags.data?.length ?? 0) > 0 && (
          <label>
            {t("graph.tag")}{" "}
            <select value={tag} onChange={(event) => setTag(event.target.value)} aria-label={t("graph.tagFilter")}>
              <option value="">{t("common.all")}</option>
              {tags.data!.map((item) => (
                <option key={item.concept_id} value={item.label}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          <input type="checkbox" checked={showIsolated} onChange={(event) => setShowIsolated(event.target.checked)} />{" "}
          {t("graph.showIsolated")}
        </label>
      </div>

      {graph.isPending && <p role="status">{t("graph.loading")}</p>}
      {graph.isError && <p role="alert">{t("graph.loadError")}</p>}
      {graph.data && (
        <>
          {graph.data.state === "partial" && (
            <p role="status" data-testid="graph-state">
              {t("graph.partial")}
            </p>
          )}
          {graph.data.nodes.length === 0 ? (
            <p data-testid="graph-empty">
              {graph.data.hidden_isolated > 0
                ? t("graph.onlyIsolated", { count: graph.data.hidden_isolated })
                : type || typed || tag
                  ? t("graph.noMatch")
                  : t("graph.empty")}
            </p>
          ) : (
            <>
              {graph.data.truncated && (
                <p className="meta" data-testid="graph-truncated">
                  {t("graph.truncated", { shown: graph.data.nodes.length, total: graph.data.total_nodes })}
                </p>
              )}
              {graph.data.hidden_isolated > 0 && (
                <p className="meta" data-testid="graph-hidden">
                  {t("graph.hidden", { count: graph.data.hidden_isolated })}
                </p>
              )}
              <div className="concept-layout">
                <ConceptGraph graph={graph.data} selectedId={selected} onSelect={setSelected} />
                {selected && (
                  <ConceptInspector conceptId={selected} onSelect={setSelected} onClose={() => setSelected(null)} />
                )}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
