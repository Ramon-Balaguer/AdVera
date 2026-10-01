import { expect, type Page, test } from "@playwright/test";

// Manual tags (ADR 0013) and the read-only concept graph (ADR 0019); the backend is mocked.
const MEETING_ID = "77777777-7777-4777-8777-777777777777";
const OTHER_ID = "88888888-8888-4888-8888-888888888888";

interface TagState {
  assignment_id: string;
  concept_id: string;
  label: string;
}

function meeting(id: string, title: string, tags: TagState[]) {
  return {
    id, title, description: null, status: "ready", started_at: null, ended_at: null, duration: 30,
    primary_language: ["ca"], created_by: null, created_at: "2026-09-30T10:00:00Z",
    updated_at: "2026-09-30T10:00:00Z", attendee_count: 2, tracks: [], tags,
  };
}

async function baseMocks(page: Page) {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
}

test("tags are added, suggested, removed and shown with their errors", async ({ page }) => {
  await baseMocks(page);
  let tags: TagState[] = [];
  let counter = 0;
  const posted: string[] = [];
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) =>
    route.fulfill({ json: meeting(MEETING_ID, "Reunió de seguiment", tags) }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) => route.fulfill({ status: 404, json: { detail: "X" } }));
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) => route.fulfill({ status: 404, json: { detail: "X" } }));
  await page.route("**/api/meetings/*/brain", (route) =>
    route.fulfill({ json: { meeting_id: MEETING_ID, state: "blocked", llm_configured: false } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/tags/suggestions**`, (route) => {
    const q = new URL(route.request().url()).searchParams.get("q") ?? "";
    const all = [{ concept_id: "c-pre", label: "Presupuesto", meetings: 3 }];
    return route.fulfill({ json: all.filter((item) => item.label.toLowerCase().includes(q.toLowerCase())) });
  });
  await page.route(`**/api/meetings/${MEETING_ID}/tags`, async (route) => {
    const label: string = route.request().postDataJSON().label;
    posted.push(label);
    if (label === "...") return route.fulfill({ status: 422, json: { detail: "INVALID_TAG" } });
    if (label === "una más") return route.fulfill({ status: 409, json: { detail: "TOO_MANY_TAGS" } });
    const existing = tags.find((tag) => tag.label.toLowerCase() === label.toLowerCase());
    if (existing) return route.fulfill({ status: 200, json: existing });
    counter += 1;
    const created = { assignment_id: `a-${counter}`, concept_id: `c-${counter}`, label };
    tags = [...tags, created];
    return route.fulfill({ status: 201, json: created });
  });
  await page.route(`**/api/meetings/${MEETING_ID}/tags/*`, (route) => {
    const id = route.request().url().split("/").pop();
    if (route.request().method() === "DELETE") {
      const found = tags.some((tag) => tag.assignment_id === id);
      tags = tags.filter((tag) => tag.assignment_id !== id);
      return route.fulfill(found ? { status: 204 } : { status: 404, json: { detail: "TAG_NOT_FOUND" } });
    }
    return route.fallback();
  });

  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByText("Sin etiquetas.")).toBeVisible();

  // Typing shows the existing tags that match; choosing one reuses it instead of retyping.
  const input = page.getByLabel("Añadir etiqueta");
  await input.fill("pre");
  await page.getByRole("button", { name: "Presupuesto (3)" }).click();
  await expect(page.getByTestId("meeting-tags")).toContainText("Presupuesto");
  await expect(input).toHaveValue("");

  // Free text with Enter; the same tag in another case is not added twice.
  const submitted = () =>
    page.waitForResponse((r) => r.url().endsWith("/tags") && r.request().method() === "POST");
  await input.fill("Lanzamiento");
  await Promise.all([submitted(), input.press("Enter")]);
  await expect(page.getByTestId("meeting-tags").getByRole("listitem")).toHaveCount(2);
  await input.fill("LANZAMIENTO");
  await Promise.all([submitted(), input.press("Enter")]);
  await expect(input).toHaveValue("");
  await expect(page.getByTestId("meeting-tags").getByRole("listitem")).toHaveCount(2);

  // Invalid and over-the-limit tags show an actionable message and keep the current tags.
  await input.fill("demasiado-larga".repeat(10)); // over 60 characters: refused without a request
  await page.getByRole("button", { name: "Añadir", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("La etiqueta no es válida");
  await input.fill("...");  // accepted by the form, refused by the server
  await Promise.all([submitted(), input.press("Enter")]);
  await expect(page.getByRole("alert")).toContainText("La etiqueta no es válida");
  await input.fill("una más");
  await Promise.all([submitted(), input.press("Enter")]);
  await expect(page.getByRole("alert")).toContainText("máximo de 20 etiquetas");
  await expect(page.getByTestId("meeting-tags").getByRole("listitem")).toHaveCount(2);

  // They survive a reload, and removing one removes only that tag.
  await page.reload();
  await expect(page.getByTestId("meeting-tags")).toContainText("Lanzamiento");
  await page.getByRole("button", { name: "Quitar etiqueta Presupuesto" }).click();
  await expect(page.getByTestId("meeting-tags").getByRole("listitem")).toHaveCount(1);
  await expect(page.getByTestId("meeting-tags")).not.toContainText("Presupuesto");
  expect(posted).toContain("Lanzamiento");
  expect(posted.some((label) => label.length > 60)).toBe(false); // the long one never left the browser
});

test("the meeting list shows tags and filters by one", async ({ page }) => {
  await baseMocks(page);
  // The shared tag is "Arquitectura", but this meeting was tagged typing "arquitectura": the
  // filter matches the shared concept, not the spelling.
  const tagged = [{ assignment_id: "a1", concept_id: "c1", label: "arquitectura" }];
  await page.route("**/api/meetings", (route) =>
    route.fulfill({ json: [meeting(MEETING_ID, "Con etiqueta", tagged), meeting(OTHER_ID, "Sin etiqueta", [])] }),
  );
  await page.route("**/api/meetings/tags", (route) =>
    route.fulfill({ json: [{ concept_id: "c1", label: "Arquitectura", meetings: 1 }] }),
  );
  await page.goto("/meetings");
  await expect(page.getByRole("row", { name: /Con etiqueta.*arquitectura/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sin etiqueta" })).toBeVisible();

  await page.getByLabel("Etiqueta").selectOption({ label: "Arquitectura (1)" });
  await expect(page.getByRole("link", { name: "Con etiqueta" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sin etiqueta" })).toHaveCount(0);
});

const GRAPH = {
  state: "ready",
  total_nodes: 3,
  truncated: false,
  nodes: [
    { id: "k", type: "technology", label: "Kafka", meetings: 2, mentions: 2, is_tag: false },
    { id: "m", type: "topic", label: "Mensajería", meetings: 1, mentions: 1, is_tag: false },
    { id: "t", type: "tag", label: "Arquitectura", meetings: 1, mentions: 0, is_tag: true },
  ],
  edges: [
    { id: "e1", source: "k", target: "m", type: "part_of", source_type: "brain", occurrences: 1, meetings: 1 },
    { id: "e2", source: "t", target: "k", type: "related_to", source_type: "manual_user", occurrences: 0, meetings: 0 },
  ],
};

const DETAIL = {
  id: "k", type: "technology", label: "Kafka", is_tag: false, aliases: ["Apache Kafka"],
  meetings: [
    {
      meeting_id: MEETING_ID, title: "Reunió de seguiment", created_at: "2026-09-30T10:00:00Z", mention: "Kafka", tagged: false,
      evidence: [{ segment_id: "system-00002", start: 12.4, text: "Proposem usar Kafka per a la mensajería." }],
    },
    { meeting_id: OTHER_ID, title: "Arquitectura", created_at: "2026-09-29T10:00:00Z", mention: null, tagged: true, evidence: [] },
  ],
  relations: [
    {
      id: "e1", direction: "outgoing", type: "part_of", source_type: "brain", other_id: "m", other_label: "Mensajería",
      other_type: "topic", meetings: ["Reunió de seguiment"], evidence: [],
    },
  ],
};

async function memoryMocks(page: Page) {
  await baseMocks(page);
  await page.route("**/api/memory/overview", (route) =>
    route.fulfill({ json: { state: "ready", meetings_indexed: 2, chunks: 9, embedded_chunks: 9, jobs_pending: 0, jobs_failed: 0, llm_configured: true } }),
  );
  await page.route("**/api/meetings/tags", (route) =>
    route.fulfill({ json: [{ concept_id: "t", label: "Arquitectura", meetings: 1 }] }),
  );
}

test("the concept graph shows concepts, filters on the server and opens an inspector with citations", async ({ page }) => {
  await memoryMocks(page);
  const requests: string[] = [];
  await page.route("**/api/memory/concept-graph**", (route) => {
    requests.push(new URL(route.request().url()).search);
    return route.fulfill({ json: GRAPH });
  });
  await page.route("**/api/memory/concepts/k", (route) => route.fulfill({ json: DETAIL }));
  await page.route("**/api/memory/concepts/m", (route) =>
    route.fulfill({ json: { ...DETAIL, id: "m", label: "Mensajería", type: "topic", aliases: [], meetings: [], relations: [] } }),
  );

  await page.goto("/memory");
  const graph = page.getByTestId("concept-graph");
  await expect(graph).toHaveAttribute("data-nodes", "3");
  await expect(graph).toHaveAttribute("data-edges", "2");
  await expect(page.getByRole("img", { name: /3 conceptos y 2 relaciones/ })).toBeVisible();
  // The minimap sits over the canvas, bottom right, and moving on it pans the graph.
  const minimap = page.getByTestId("concept-minimap");
  await expect(minimap).toBeVisible();
  const [canvasBox, mapBox] = [await graph.boundingBox(), await minimap.boundingBox()];
  expect(mapBox!.x + mapBox!.width).toBeGreaterThan(canvasBox!.x + canvasBox!.width - 20);
  expect(mapBox!.y + mapBox!.height).toBeGreaterThan(canvasBox!.y + canvasBox!.height - 20);
  await minimap.click({ position: { x: 4, y: 4 } });

  // Selecting a concept opens its inspector: aliases, meetings, the cited moment and relations.
  await page.getByTestId("concept-list").getByRole("button", { name: /Kafka/ }).click();
  const inspector = page.getByTestId("concept-inspector");
  await expect(inspector).toContainText("Tecnología · también: Apache Kafka");
  await expect(inspector.getByText("Proposem usar Kafka per a la mensajería.")).toBeVisible();
  const moment = inspector.getByRole("link", { name: "00:12" });
  await expect(moment).toHaveAttribute("href", /\/meetings\/77777777.*at=12.*segment=system-00002.*play=1/);
  await expect(inspector).toContainText("etiqueta manual (sin evidencia del transcript)");
  await expect(inspector).toContainText("es parte de");

  // A related concept can be followed from the inspector.
  await inspector.getByRole("button", { name: "Mensajería" }).click();
  await expect(page.getByTestId("concept-inspector")).toContainText("Mensajería");
  await page.getByRole("button", { name: "Cerrar el inspector" }).click();
  await expect(page.getByTestId("concept-inspector")).toHaveCount(0);

  // Filters are sent to the server (nothing is filtered in the browser).
  await page.getByLabel("Tipo").selectOption("topic");
  await expect.poll(() => requests.some((search) => search.includes("type=topic"))).toBe(true);
  await page.getByPlaceholder("Buscar concepto…").fill("kaf");
  await expect.poll(() => requests.some((search) => search.includes("q=kaf"))).toBe(true);
  await page.getByLabel("Etiqueta del grafo").selectOption("Arquitectura");
  await expect.poll(() => requests.some((search) => search.includes("tag=Arquitectura"))).toBe(true);
});

test("the graph says when it is empty, partial, truncated or failing", async ({ page }) => {
  await memoryMocks(page);
  let response: { status?: number; json: unknown } = {
    json: { state: "empty", nodes: [], edges: [], total_nodes: 0, truncated: false },
  };
  await page.route("**/api/memory/concept-graph**", (route) => route.fulfill(response));

  await page.goto("/memory");
  await expect(page.getByTestId("graph-empty")).toContainText("Todavía no hay conceptos");

  response = { json: { ...GRAPH, state: "partial", truncated: true, total_nodes: 240 } };
  await page.getByLabel("Tipo").selectOption("topic");
  await expect(page.getByTestId("graph-state")).toContainText("todavía puede crecer");
  await expect(page.getByTestId("graph-truncated")).toContainText("3 conceptos más compartidos de 240");

  response = { json: { state: "ready", nodes: [], edges: [], total_nodes: 0, truncated: false } };
  await page.getByLabel("Tipo").selectOption("person");
  await expect(page.getByTestId("graph-empty")).toContainText("Ningún concepto coincide con los filtros");

  response = { status: 500, json: { detail: "X" } };
  await page.getByLabel("Tipo").selectOption("project");
  await expect(page.getByRole("alert")).toContainText("No se pudo cargar el grafo", { timeout: 10_000 });
});

test("concepts without relationships are hidden by default, counted, and shown on request", async ({ page }) => {
  await memoryMocks(page);
  const requests: string[] = [];
  await page.route("**/api/memory/concept-graph**", (route) => {
    const search = new URL(route.request().url()).search;
    requests.push(search);
    const hiding = search.includes("include_isolated=false");
    return route.fulfill({
      json: hiding
        ? { state: "ready", nodes: [], edges: [], total_nodes: 0, truncated: false, hidden_isolated: 4 }
        : { ...GRAPH, hidden_isolated: 0 },
    });
  });

  await page.goto("/memory");
  await expect(page.getByTestId("graph-empty")).toContainText("Hay 4 conceptos, pero ninguno tiene relaciones");
  expect(requests[0]).toContain("include_isolated=false");

  await page.getByLabel("Mostrar conceptos sin relaciones").check();
  await expect(page.getByTestId("concept-graph")).toHaveAttribute("data-nodes", "3");
  await expect(page.getByTestId("graph-hidden")).toHaveCount(0);

  // A search always includes loose concepts, so any concept can be found.
  await page.getByLabel("Mostrar conceptos sin relaciones").uncheck();
  await page.getByPlaceholder("Buscar concepto…").fill("presu");
  await expect.poll(() => requests.some((q) => q.includes("q=presu") && !q.includes("include_isolated"))).toBe(true);
});

test("a tag chosen in the question form is sent as a search filter", async ({ page }) => {
  await memoryMocks(page);
  await page.route("**/api/memory/concept-graph**", (route) =>
    route.fulfill({ json: { state: "empty", nodes: [], edges: [], total_nodes: 0, truncated: false } }),
  );
  let posted: Record<string, unknown> | null = null;
  await page.route("**/api/memory/query", (route) => {
    posted = route.request().postDataJSON();
    return route.fulfill({
      status: 202,
      json: { query_id: "q-1", query: "q", status: "empty", error: null, result: { answer: null, sources: [], retrieved: [], reason: "NO_MATCH" } },
    });
  });
  await page.goto("/memory");
  await page.getByLabel("¿Qué quieres saber de tus reuniones?").fill("¿Qué se decidió?");
  await page.getByLabel("Filtrar la búsqueda por etiqueta").selectOption("Arquitectura");
  await page.getByRole("button", { name: "Preguntar" }).click();
  await expect.poll(() => posted).not.toBeNull();
  expect(posted).toMatchObject({ query: "¿Qué se decidió?", filters: { tag: "Arquitectura" } });
});
