import cytoscape from "cytoscape";
import { useEffect, useMemo, useRef } from "react";

import { type ConceptGraphData, RELATION_LABELS, TYPE_COLORS } from "./conceptGraphApi";

// Read-only view of the concept graph (concept-graph.md): zoom, drag and select; no editing.
// A list of the same concepts is rendered beside the canvas: it is the keyboard and screen
// reader way to select a node, and what the tests use.
export function ConceptGraph({
  graph,
  selectedId,
  onSelect,
}: {
  graph: ConceptGraphData;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<cytoscape.Core | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;

  // The layout runs again only when what is drawn changes: a refetch with the same nodes and
  // edges (every 10 s while processing) must not reset the user's zoom and pan.
  const shape = useMemo(
    () =>
      JSON.stringify([
        graph.nodes.map((n) => [n.id, n.label, n.type, n.meetings, n.is_tag]),
        graph.edges.map((e) => [e.id, e.source, e.target, e.type, e.source_type]),
      ]),
    [graph],
  );
  const current = useRef(graph);
  current.current = graph;

  useEffect(() => {
    if (!container.current) return;
    const graph = current.current;
    const text = getComputedStyle(container.current).color || "#888";
    const cy = cytoscape({
      container: container.current,
      elements: [
        ...graph.nodes.map((node) => ({
          data: { id: node.id, label: node.label, type: node.type, meetings: node.meetings },
          classes: node.is_tag ? "tag" : "",
        })),
        ...graph.edges.map((edge) => ({
          data: { id: edge.id, source: edge.source, target: edge.target, label: RELATION_LABELS[edge.type] ?? edge.type },
          classes: edge.source_type === "manual_user" ? "manual" : "",
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            color: text,
            "font-size": 11,
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: "mapData(meetings, 1, 10, 18, 46)",
            height: "mapData(meetings, 1, 10, 18, 46)",
            "background-color": (element: cytoscape.NodeSingular) => TYPE_COLORS[element.data("type")] ?? "#64748b",
          },
        },
        { selector: "node.tag", style: { shape: "round-rectangle", "border-width": 2, "border-color": text } },
        { selector: "node.selected", style: { "border-width": 3, "border-color": "#f59e0b" } },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 9,
            color: text,
            "text-rotation": "autorotate",
          },
        },
        { selector: "edge.manual", style: { "line-style": "dashed" } },
      ],
      layout: { name: "cose", animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 90 },
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.25,
    });
    cy.on("tap", "node", (event) => select.current(event.target.id()));
    cy.on("tap", (event) => {
      if (event.target === cy) select.current(null);
    });
    instance.current = cy;
    return () => {
      cy.destroy();
      instance.current = null;
    };
  }, [shape]);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    cy.nodes().removeClass("selected");
    if (selectedId) cy.getElementById(selectedId).addClass("selected");
  }, [selectedId, shape]);

  return (
    <div className="concept-graph">
      <div
        ref={container}
        className="concept-canvas"
        data-testid="concept-graph"
        data-nodes={graph.nodes.length}
        data-edges={graph.edges.length}
        role="img"
        aria-label={`Grafo de conceptos: ${graph.nodes.length} conceptos y ${graph.edges.length} relaciones`}
      />
      <ul className="concept-list" data-testid="concept-list" aria-label="Conceptos del grafo">
        {graph.nodes.map((node) => (
          <li key={node.id}>
            <button
              type="button"
              aria-pressed={node.id === selectedId}
              onClick={() => onSelect(node.id === selectedId ? null : node.id)}
            >
              <span className="swatch" style={{ background: TYPE_COLORS[node.type] ?? "#64748b" }} aria-hidden="true" />
              {node.label}
              <span className="meta">
                {" "}
                · {node.is_tag ? "etiqueta" : `${node.mentions} menciones`} · {node.meetings} reunión(es)
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
