import cytoscape from "cytoscape";
import { useEffect, useMemo, useRef } from "react";

import { type ConceptGraphData, RELATION_LABELS, TYPE_COLORS } from "./conceptGraphApi";
import { attachMinimap } from "./minimap";

// Read-only view of the concept graph (concept-graph.md): zoom, drag and select; no editing.
// A list of the same concepts is rendered beside the canvas: it is the keyboard and screen
// reader way to select a node, and what the tests use.
const DOT_STEP = 24; // board dots, in graph units
const GAP = 90; // between groups and rings
const RING_SPACING = 55; // between loose concepts on a ring

type Group = { nodes: cytoscape.NodeCollection; radius: number };

// Radial arrangement (operator request, after a picture of a radial graph): the concept with
// most relationships in the middle with its group laid out around it, the other connected
// groups on a ring around that, and concepts without relationships on the outer rings.
function arrangeRadially(cy: cytoscape.Core) {
  const nodes = cy.nodes();
  if (nodes.empty()) return;
  const hub = nodes.max((node) => node.degree(false) * 1000 + Number(node.data("meetings") ?? 0)).ele;
  const loose = nodes.filter((node) => node.degree(false) === 0);
  const groups: Group[] = [];
  let main: Group | null = null;
  for (const component of cy.elements().components()) {
    const members = component.nodes();
    if (members.length === 1 && members[0].degree(false) === 0) continue;
    // Centre each group on its own middle (the main group on the hub) and measure it.
    const centre = members.contains(hub) ? hub.position() : middle(members);
    members.shift({ x: -centre.x, y: -centre.y });
    const radius = Math.max(...members.map((node) => Math.hypot(node.position("x"), node.position("y")))) + 30;
    const group = { nodes: members, radius };
    if (members.contains(hub)) main = group;
    else groups.push(group);
  }
  let reach = main ? main.radius : 0;

  if (groups.length) {
    groups.sort((a, b) => b.radius - a.radius);
    const widest = groups[0].radius;
    const around = groups.reduce((sum, group) => sum + 2 * group.radius + GAP, 0);
    const ring = Math.max(reach + GAP + widest, around / (2 * Math.PI));
    let angle = -Math.PI / 2;
    for (const group of groups) {
      const share = (2 * group.radius + GAP) / ring; // radians taken on the ring
      angle += share / 2;
      group.nodes.shift({ x: ring * Math.cos(angle), y: ring * Math.sin(angle) });
      angle += share / 2;
    }
    reach = ring + widest;
  }

  const sorted = loose.sort((a, b) =>
    `${a.data("type")} ${a.data("label")}`.localeCompare(`${b.data("type")} ${b.data("label")}`),
  );
  let ring = reach + GAP;
  let index = 0;
  while (index < sorted.length) {
    const capacity = Math.max(8, Math.floor((2 * Math.PI * ring) / RING_SPACING));
    const onRing = sorted.slice(index, index + capacity);
    onRing.forEach((node, position) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * position) / onRing.length;
      node.position({ x: ring * Math.cos(angle), y: ring * Math.sin(angle) });
    });
    index += onRing.length;
    ring += RING_SPACING;
  }
}

function middle(nodes: cytoscape.NodeCollection) {
  const box = nodes.boundingBox();
  return { x: box.x1 + box.w / 2, y: box.y1 + box.h / 2 };
}

// Focus: a node (hovered or selected) with its neighbours and their edges stands out, the
// rest fades, and only the focused edges show what relation they are.
function applyFocus(cy: cytoscape.Core, id: string | null) {
  cy.elements().removeClass("focus faded");
  if (!id) return;
  const node = cy.getElementById(id);
  if (node.empty()) return;
  const near = node.closedNeighborhood();
  near.addClass("focus");
  cy.elements().difference(near).addClass("faded");
}

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
  const minimap = useRef<HTMLCanvasElement>(null);
  const instance = useRef<cytoscape.Core | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  const focused = useRef(selectedId);
  focused.current = selectedId;

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
            "font-size": 9,
            "min-zoomed-font-size": 7, // names appear as you zoom in
            "text-valign": "bottom",
            "text-margin-y": 3,
            "text-background-color": "#0f172a",
            "text-background-opacity": 0.55,
            "text-background-padding": "1px",
            width: "mapData(meetings, 1, 10, 9, 26)",
            height: "mapData(meetings, 1, 10, 9, 26)",
            "background-color": (element: cytoscape.NodeSingular) => TYPE_COLORS[element.data("type")] ?? "#64748b",
          },
        },
        { selector: "node.tag", style: { shape: "round-rectangle", "border-width": 1.5, "border-color": text } },
        {
          selector: "edge",
          style: {
            width: 0.8,
            opacity: 0.45,
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.6,
            "curve-style": "bezier",
            "font-size": 8,
            color: text,
            "text-rotation": "autorotate",
            "text-background-color": "#0f172a",
            "text-background-opacity": 0.7,
            "text-background-padding": "1px",
          },
        },
        { selector: "edge.manual", style: { "line-style": "dashed" } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: "node.focus", style: { "min-zoomed-font-size": 0, "font-size": 10, "z-index": 10 } },
        { selector: "edge.focus", style: { opacity: 1, width: 1.4, label: "data(label)", "z-index": 9 } },
        { selector: "node.selected", style: { "border-width": 3, "border-color": "#f59e0b" } },
      ],
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 3.5, // the operator asked three times for a faster wheel zoom
    });
    // cose gives each connected group its shape; the groups and the loose concepts are then
    // arranged radially around the most connected concept, and the whole graph is fitted.
    const layout = cy.layout({
      name: "cose",
      animate: false,
      fit: false,
      nodeRepulsion: () => 60000,
      idealEdgeLength: () => 110,
      nodeOverlap: 30,
    });
    layout.one("layoutstop", () => {
      arrangeRadially(cy);
      cy.fit(undefined, 30);
    });
    layout.run();
    // Keep the canvas size current; a graph laid out while hidden is fitted when it appears.
    let empty = cy.width() === 0;
    const observer = new ResizeObserver(() => {
      cy.resize();
      if (empty && cy.width() > 0) cy.fit(undefined, 30);
      empty = cy.width() === 0;
    });
    observer.observe(container.current);
    const detachMinimap = minimap.current ? attachMinimap(cy, minimap.current) : () => undefined;
    // A dotted board that moves and scales with the view, so dragging it is visible.
    const board = container.current;
    const moveBoard = () => {
      const step = Math.max(6, DOT_STEP * cy.zoom());
      board.style.backgroundSize = `${step}px ${step}px`;
      board.style.backgroundPosition = `${cy.pan().x}px ${cy.pan().y}px`;
    };
    cy.on("viewport resize", moveBoard);
    moveBoard();
    cy.on("mouseover", "node", (event) => applyFocus(cy, event.target.id()));
    cy.on("mouseout", "node", () => applyFocus(cy, focused.current));
    cy.on("tap", "node", (event) => select.current(event.target.id()));
    cy.on("tap", (event) => {
      if (event.target === cy) select.current(null);
    });
    instance.current = cy;
    return () => {
      observer.disconnect();
      detachMinimap();
      cy.destroy();
      instance.current = null;
    };
  }, [shape]);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    cy.nodes().removeClass("selected");
    if (selectedId) cy.getElementById(selectedId).addClass("selected");
    applyFocus(cy, selectedId);
  }, [selectedId, shape]);

  return (
    <div className="concept-graph">
      <div className="concept-stage">
        <div
          ref={container}
          className="concept-canvas"
          data-testid="concept-graph"
          data-nodes={graph.nodes.length}
          data-edges={graph.edges.length}
          role="img"
          aria-label={`Grafo de conceptos: ${graph.nodes.length} conceptos y ${graph.edges.length} relaciones`}
        />
        <canvas
          ref={minimap}
          className="concept-minimap"
          data-testid="concept-minimap"
          aria-hidden="true"
          title="Minimapa: pulsa o arrastra para moverte por el grafo"
        />
      </div>
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
