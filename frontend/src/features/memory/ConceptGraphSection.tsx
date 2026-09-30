import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../../api";
import { ConceptGraph } from "./ConceptGraph";
import { ConceptInspector } from "./ConceptInspector";
import { CONCEPT_TYPES, fetchConceptGraph, TYPE_LABELS } from "./conceptGraphApi";

const STATES: Record<string, string> = {
  partial: "Hay reuniones procesándose: el grafo todavía puede crecer.",
};

// The concept graph of all meetings, read-only (concept-graph.md). Filters run on the server.
export function ConceptGraphSection() {
  const [type, setType] = useState("");
  const [text, setText] = useState("");
  const [typed, setTyped] = useState("");
  const [tag, setTag] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.listTags });

  useEffect(() => {
    const timer = window.setTimeout(() => setTyped(text.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [text]);

  const graph = useQuery({
    queryKey: ["concept-graph", type, typed, tag],
    queryFn: () => fetchConceptGraph({ type, q: typed, tag }),
    retry: 1,
    refetchInterval: (query) => (query.state.data?.state === "partial" ? 10_000 : false),
  });

  return (
    <section className="concept-section" aria-label="Grafo de conceptos">
      <h2>Grafo de conceptos</h2>
      <div className="row">
        <label>
          Tipo{" "}
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="">Todos</option>
            {CONCEPT_TYPES.map((item) => (
              <option key={item} value={item}>
                {TYPE_LABELS[item]}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          <span className="visually-hidden">Buscar concepto</span>
          <input value={text} placeholder="Buscar concepto…" onChange={(event) => setText(event.target.value)} />
        </label>
        {(tags.data?.length ?? 0) > 0 && (
          <label>
            Etiqueta{" "}
            <select value={tag} onChange={(event) => setTag(event.target.value)} aria-label="Etiqueta del grafo">
              <option value="">Todas</option>
              {tags.data!.map((item) => (
                <option key={item.concept_id} value={item.label}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {graph.isPending && <p role="status">Cargando el grafo…</p>}
      {graph.isError && <p role="alert">No se pudo cargar el grafo de conceptos.</p>}
      {graph.data && (
        <>
          {STATES[graph.data.state] && (
            <p role="status" data-testid="graph-state">
              {STATES[graph.data.state]}
            </p>
          )}
          {graph.data.nodes.length === 0 ? (
            <p data-testid="graph-empty">
              {type || typed || tag
                ? "Ningún concepto coincide con los filtros."
                : "Todavía no hay conceptos. Aparecen al procesar reuniones con Brain o al etiquetarlas."}
            </p>
          ) : (
            <>
              {graph.data.truncated && (
                <p className="meta" data-testid="graph-truncated">
                  Mostrando los {graph.data.nodes.length} conceptos más compartidos de {graph.data.total_nodes}. Usa los
                  filtros para acotar.
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
