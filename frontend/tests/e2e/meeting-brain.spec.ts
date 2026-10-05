import { expect, test } from "./fixtures";
import type { Page } from "./fixtures";

// The Brain tab of a meeting and the facts page, with a mocked backend; synthetic data only.
const MEETING_ID = "66666666-6666-4666-8666-666666666666";

const evidence = (segment: string, start: number) => [{ segment_id: segment, start, track: "system", text: "cita" }];

function brainBody(overrides: Record<string, unknown> = {}) {
  return {
    meeting_id: MEETING_ID,
    title: "Sincro semanal",
    date: "2026-09-30T10:00:00Z",
    index: { state: "completed", error: null, completed_at: "2026-09-30T11:00:00Z", up_to_date: true, chunks: 12, embedded: 12 },
    projection: { state: "completed", error: null, completed_at: "2026-09-30T11:01:00Z", up_to_date: true },
    fact_counts: { decision: 1, action: 1, question: 1, risk: 0, topic: 0 },
    concepts: [
      { id: "c1", name: "Redis", type: "technology", mentions: 3, other_meetings: 4, first_seen: "2026-08-01T10:00:00Z" },
      { id: "c2", name: "Presupuesto", type: "topic", mentions: 1, other_meetings: 0, first_seen: "2026-09-30T10:00:00Z" },
    ],
    relationships: [{ source_id: "c1", source: "Redis", target_id: "c2", target: "Presupuesto", type: "constrains", evidence: 1 }],
    tags: [{ id: "t1", label: "Cliente", other_meetings: 1, first_seen: "2026-09-01T10:00:00Z" }],
    people: [{ id: "p1", name: "Marta", speakers: ["SPEAKER_00"], other_meetings: 2, first_seen: "2026-09-02T10:00:00Z" }],
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

  // The facts are in the summary: here they are only counted, with a way to the list.
  await expect(page.getByTestId("meeting-brain")).not.toContainText("Migrar a Redis");
  const facts = page.getByTestId("brain-facts");
  await expect(facts.getByRole("link", { name: "Ver los 3 hechos de esta reunión" })).toHaveAttribute(
    "href",
    `/brain/facts?meeting=${MEETING_ID}`,
  );
  await expect(facts.getByRole("link", { name: "Hechos de todas las reuniones" })).toHaveAttribute("href", "/brain/facts");

  await expect(page.getByTestId("meeting-concepts").getByRole("link", { name: "Redis" })).toHaveAttribute("href", "/brain/timeline/c1");
  await expect(page.getByTestId("meeting-concepts")).toContainText("3 menciones");
  // How far each one goes beyond this meeting, the ones found elsewhere first.
  await expect(page.getByTestId("meeting-concepts").locator("li").first()).toContainText("también en 4 reuniones más");
  await expect(page.getByTestId("meeting-concepts").locator("li").first()).toContainText("desde el");
  await expect(page.getByTestId("reach-none")).toHaveCount(1);
  await expect(page.getByTestId("meeting-concepts")).toContainText("solo en esta reunión");
  await expect(page.getByTestId("meeting-relationships")).toContainText("Redis");
  await expect(page.getByTestId("meeting-relationships")).toContainText("Presupuesto");
  await expect(page.getByTestId("meeting-brain").getByRole("link", { name: "Cliente" })).toHaveAttribute("href", "/brain/timeline/t1");
  await expect(page.getByTestId("meeting-brain")).toContainText("también en 1 reunión más");
  await expect(page.getByTestId("meeting-brain").getByRole("link", { name: "Marta" })).toBeVisible();
  await expect(page.getByTestId("meeting-brain")).toContainText("también en 2 reuniones más");
});

test("the Brain tab warns when the Brain has not read the meeting or it is out of date", async ({ page }) => {
  await openMeeting(
    page,
    brainBody({
      index: { state: "none", error: null, completed_at: null, up_to_date: null, chunks: 0, embedded: 0 },
      projection: { state: "none", error: null, completed_at: null, up_to_date: null },
      fact_counts: { decision: 0, action: 0, question: 0, risk: 0, topic: 0 },
      concepts: [],
      relationships: [],
      tags: [],
      people: [],
    }),
  );
  await page.getByRole("tab", { name: "Brain" }).click();
  await expect(page.getByTestId("brain-index")).toContainText("Sin indexar");
  await expect(page.getByTestId("brain-notice")).toContainText("todavía no ha leído el resumen");
  await expect(page.getByTestId("brain-facts")).toContainText("Todavía no hay decisiones, acciones, dudas, riesgos ni temas.");
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

test("the facts page can be limited to one meeting and goes back to all", async ({ page }) => {
  const asked: string[] = [];
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/meetings/tags", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/brain/facts**", (route) => {
    asked.push(new URL(route.request().url()).search);
    return route.fulfill({ json: { total: 0, counts: { decision: 0, action: 0, question: 0, risk: 0, topic: 0 }, facts: [] } });
  });
  await page.goto(`/brain/facts?meeting=${MEETING_ID}`);

  await expect(page.getByTestId("facts-one-meeting")).toContainText("Solo los hechos de una reunión.");
  await expect.poll(() => asked.at(-1)).toContain(`meeting_id=${MEETING_ID}`);
  await page.getByRole("button", { name: "Ver todas las reuniones" }).click();
  await expect(page.getByTestId("facts-one-meeting")).toHaveCount(0);
  await expect.poll(() => asked.at(-1)).not.toContain("meeting_id");
});
