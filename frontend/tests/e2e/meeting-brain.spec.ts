import { expect, test } from "./fixtures";
import type { Page } from "./fixtures";

// The Brain tab of a meeting and the facts page, with a mocked backend; synthetic data only.
const MEETING_ID = "66666666-6666-4666-8666-666666666666";

const evidence = (segment: string, start: number) => [{ segment_id: segment, start, track: "system", text: "cita" }];

function brainBody(overrides: Record<string, unknown> = {}) {
  const meeting = { meeting_id: MEETING_ID, meeting_title: "Sincro semanal", meeting_date: "2026-09-30T10:00:00Z" };
  return {
    meeting_id: MEETING_ID,
    title: "Sincro semanal",
    date: "2026-09-30T10:00:00Z",
    index: { state: "completed", error: null, completed_at: "2026-09-30T11:00:00Z", up_to_date: true, chunks: 12, embedded: 12 },
    projection: { state: "completed", error: null, completed_at: "2026-09-30T11:01:00Z", up_to_date: true },
    facts: {
      decision: [{ id: "d1", kind: "decision", text: "Migrar a Redis", state: "decided", evidence: evidence("system-00001", 12), ...meeting }],
      action: [{ id: "a1", kind: "action", text: "Preparar el informe", owner: "Marta", due_date: "viernes", evidence: evidence("system-00002", 30), ...meeting }],
      question: [{ id: "q1", kind: "question", text: "¿Quién paga la GPU?", evidence: [], ...meeting }],
      risk: [],
      topic: [],
    },
    concepts: [
      { id: "c1", name: "Redis", type: "technology", mentions: 3 },
      { id: "c2", name: "Presupuesto", type: "topic", mentions: 1 },
    ],
    relationships: [{ source_id: "c1", source: "Redis", target_id: "c2", target: "Presupuesto", type: "constrains", evidence: 1 }],
    tags: ["Cliente"],
    people: [{ id: "p1", name: "Marta", speakers: ["SPEAKER_00"] }],
    ...overrides,
  };
}

async function openMeeting(page: Page, body: unknown) {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) =>
    route.fulfill({
      json: {
        id: MEETING_ID, title: "Sincro semanal", description: null, status: "ready", started_at: null, ended_at: null,
        duration: 20, primary_language: ["es"], created_by: null, created_at: "2026-09-30T10:00:00Z",
        updated_at: "2026-09-30T10:00:00Z", attendee_count: 1, tracks: [],
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) => route.fulfill({ status: 404, json: {} }));
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) => route.fulfill({ status: 404, json: {} }));
  await page.route(`**/api/meetings/${MEETING_ID}/summary`, (route) =>
    route.fulfill({ json: { meeting_id: MEETING_ID, state: "not_started", llm_configured: true } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/brain`, (route) => route.fulfill({ json: body }));
  await page.goto(`/meetings/${MEETING_ID}`);
}

test("the Brain tab shows the index, the facts, the concepts and who took part", async ({ page }) => {
  await openMeeting(page, brainBody());

  // The summary stays the first tab.
  await expect(page.getByRole("tab", { name: "Resumen" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Brain" }).click();

  await expect(page.getByTestId("brain-index")).toContainText("Indexada");
  await expect(page.getByTestId("brain-index")).toContainText("12 fragmentos, 12 con embeddings");
  await expect(page.getByTestId("brain-notice")).toHaveCount(0);

  const decisions = page.getByTestId("facts-decision");
  await expect(decisions).toContainText("Migrar a Redis");
  await expect(decisions).toContainText("Decidida");
  await expect(decisions.getByRole("link", { name: "00:12" })).toHaveAttribute("href", /at=12.*segment=system-00001.*play=1/);
  await expect(page.getByTestId("facts-action")).toContainText("Responsable: Marta");
  await expect(page.getByTestId("facts-action")).toContainText("Fecha: viernes");
  await expect(page.getByTestId("facts-question")).toContainText("¿Quién paga la GPU?");
  await expect(page.getByTestId("facts-risk")).toHaveCount(0); // a kind with nothing is not listed

  await expect(page.getByTestId("meeting-concepts").getByRole("link", { name: "Redis" })).toHaveAttribute("href", "/brain/timeline/c1");
  await expect(page.getByTestId("meeting-concepts")).toContainText("3 menciones");
  await expect(page.getByTestId("meeting-relationships")).toContainText("Redis");
  await expect(page.getByTestId("meeting-relationships")).toContainText("Presupuesto");
  await expect(page.getByTestId("meeting-brain")).toContainText("Cliente");
  await expect(page.getByTestId("meeting-brain").getByRole("link", { name: "Marta" })).toBeVisible();
});

test("the Brain tab warns when the Brain has not read the meeting or it is out of date", async ({ page }) => {
  await openMeeting(
    page,
    brainBody({
      index: { state: "none", error: null, completed_at: null, up_to_date: null, chunks: 0, embedded: 0 },
      projection: { state: "none", error: null, completed_at: null, up_to_date: null },
      facts: { decision: [], action: [], question: [], risk: [], topic: [] },
      concepts: [],
      relationships: [],
      tags: [],
      people: [],
    }),
  );
  await page.getByRole("tab", { name: "Brain" }).click();
  await expect(page.getByTestId("brain-index")).toContainText("Sin indexar");
  await expect(page.getByTestId("brain-notice")).toContainText("todavía no ha leído el resumen");
  await expect(page.getByText("Todavía no hay decisiones, acciones, dudas, riesgos ni temas.")).toBeVisible();
});

test("an out-of-date projection and a failed index are told in words", async ({ page }) => {
  await openMeeting(
    page,
    brainBody({
      index: { state: "failed", error: "LEASE_EXPIRED", completed_at: null, up_to_date: false, chunks: 0, embedded: 0 },
      projection: { state: "completed", error: null, completed_at: null, up_to_date: false },
    }),
  );
  await page.getByRole("tab", { name: "Brain" }).click();
  await expect(page.getByTestId("brain-index")).toContainText("Falló el indexado");
  await expect(page.getByTestId("brain-notice")).toContainText("cambiaron desde que el Brain los leyó");
});

test("the facts page filters by kind and state and opens the cited second", async ({ page }) => {
  const asked: string[] = [];
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/meetings/tags", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/brain/facts**", (route) => {
    const url = new URL(route.request().url());
    asked.push(url.search);
    const kind = url.searchParams.get("kind");
    const meeting = { meeting_id: MEETING_ID, meeting_title: "Sincro semanal", meeting_date: "2026-09-30T10:00:00Z" };
    const rows =
      kind === "decision" && url.searchParams.get("state") !== "rejected"
        ? [{ id: "d1", kind, text: "Migrar a Redis", state: "decided", evidence: evidence("system-00001", 12), ...meeting }]
        : [];
    return route.fulfill({ json: { total: rows.length, counts: { decision: 1, action: 0, question: 0, risk: 0, topic: 0 }, facts: rows } });
  });
  await page.goto("/brain/facts");

  await expect(page.getByRole("heading", { name: "Hechos" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Decisiones (1)" })).toHaveAttribute("aria-selected", "true");
  const row = page.getByTestId("fact-decision");
  await expect(row).toContainText("Migrar a Redis");
  await expect(row.getByRole("link", { name: "Sincro semanal" })).toHaveAttribute("href", `/meetings/${MEETING_ID}`);
  await expect(row.getByRole("link", { name: "00:12" })).toHaveAttribute("href", /segment=system-00001/);

  await page.getByLabel("Estado").selectOption("rejected");
  await expect.poll(() => asked.at(-1)).toContain("state=rejected");
  await expect(page.getByTestId("facts-empty")).toContainText("Ningún hecho coincide.");

  await page.getByRole("tab", { name: /Acciones/ }).click();
  await expect.poll(() => asked.at(-1)).toContain("kind=action");
  await expect(page.getByPlaceholder("Responsable…")).toBeVisible();
});
