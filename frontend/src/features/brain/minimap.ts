import type cytoscape from "cytoscape";

import { TYPE_COLORS } from "./conceptGraphApi";

const PADDING = 6;

// A small overview of the whole graph with the visible area outlined, so the user knows where
// they are while zoomed in (operator request). Clicking or dragging on it moves the view there.
// It only reads the graph; the keyboard way to move around stays the concept list.
export function attachMinimap(cy: cytoscape.Core, canvas: HTMLCanvasElement): () => void {
  const context = canvas.getContext("2d");
  if (!context) return () => undefined;
  const ratio = window.devicePixelRatio || 1;
  let frame = 0;

  // Model coordinates -> minimap pixels, from the bounding box of the whole graph.
  const transform = () => {
    const box = cy.elements().boundingBox();
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const scale = Math.min((width - 2 * PADDING) / Math.max(box.w, 1), (height - 2 * PADDING) / Math.max(box.h, 1));
    const offsetX = (width - box.w * scale) / 2 - box.x1 * scale;
    const offsetY = (height - box.h * scale) / 2 - box.y1 * scale;
    return { scale, offsetX, offsetY };
  };

  const draw = () => {
    frame = 0;
    if (cy.destroyed()) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (canvas.width !== width * ratio || canvas.height !== height * ratio) {
      canvas.width = width * ratio;
      canvas.height = height * ratio;
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    if (cy.nodes().empty()) return;
    const { scale, offsetX, offsetY } = transform();
    const at = (point: cytoscape.Position) => [point.x * scale + offsetX, point.y * scale + offsetY];

    context.strokeStyle = "rgba(148, 163, 184, 0.5)";
    context.lineWidth = 0.6;
    cy.edges().forEach((edge) => {
      const [x1, y1] = at(edge.source().position());
      const [x2, y2] = at(edge.target().position());
      context.beginPath();
      context.moveTo(x1, y1);
      context.lineTo(x2, y2);
      context.stroke();
    });
    cy.nodes().forEach((node) => {
      const [x, y] = at(node.position());
      context.fillStyle = TYPE_COLORS[node.data("type")] ?? "#9a9a9a";
      context.beginPath();
      context.arc(x, y, 2, 0, 2 * Math.PI);
      context.fill();
    });

    const view = cy.extent();
    context.strokeStyle = "#ffb829";
    context.lineWidth = 1.5;
    context.strokeRect(view.x1 * scale + offsetX, view.y1 * scale + offsetY, view.w * scale, view.h * scale);
  };

  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(draw);
  };

  // Centre the main view on the clicked point of the minimap.
  const moveTo = (event: PointerEvent) => {
    const rect = canvas.getBoundingClientRect();
    const { scale, offsetX, offsetY } = transform();
    const x = (event.clientX - rect.left - offsetX) / scale;
    const y = (event.clientY - rect.top - offsetY) / scale;
    const zoom = cy.zoom();
    cy.pan({ x: cy.width() / 2 - x * zoom, y: cy.height() / 2 - y * zoom });
  };
  let dragging = false;
  const down = (event: PointerEvent) => {
    dragging = true;
    canvas.setPointerCapture(event.pointerId);
    moveTo(event);
  };
  const move = (event: PointerEvent) => {
    if (dragging) moveTo(event);
  };
  const up = () => {
    dragging = false;
  };

  cy.on("viewport position add remove resize layoutstop", schedule);
  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointercancel", up);
  schedule();

  return () => {
    if (frame) cancelAnimationFrame(frame);
    if (!cy.destroyed()) cy.off("viewport position add remove resize layoutstop", schedule);
    canvas.removeEventListener("pointerdown", down);
    canvas.removeEventListener("pointermove", move);
    canvas.removeEventListener("pointerup", up);
    canvas.removeEventListener("pointercancel", up);
  };
}
