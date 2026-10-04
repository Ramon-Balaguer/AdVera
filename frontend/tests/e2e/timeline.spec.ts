import { expect, test } from "./fixtures";

// Timeline of a concept across meetings (rebuild-concept-timeline.md); backend mocked.
const CONCEPT = "c-pressupost";
const JAN = "11111111-1111-4111-8111-111111111111";
const FEB = "22222222-2222-4222-8222-222222222222";

test("a concept's timeline lists its meetings newest first with facts and cited moments", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route(`**/api/brain/concepts/${CONCEPT}/timeline`, (route) =>
    route.fulfill({
      json: {
        concept_id: CONCEPT, label: "Pressupost", type: "topic", is_tag: false, truncated: false,
        entries: [
          {
            meeting_id: FEB, title: "Febrer", date: "2026-02-12T10:00:00Z", mentioned: true, tagged: false, spoke: false,
            quotes: [],
            facts: [{ kind: "action", text: "Enviar el pressupost nou", state: null, owner: "Marta", due_date: "divendres",
              evidence: [{ segment_id: "note-002", start: null, track: "notes", text: "Enviar-lo divendres." }] }],
            summary: null,
          },
          {
            meeting_id: JAN, title: "Gener", date: "2026-01-15T10:00:00Z", mentioned: true, tagged: false, spoke: false,
            quotes: [{ segment_id: "system-00003", start: 75, track: "system", text: "El pressupost inicial és de deu mil." }],
            facts: [{ kind: "decision", text: "Aprovar el pressupost inicial", state: "decided", owner: null, due_date: null,
              evidence: [{ segment_id: "system-00003", start: 75, track: "system", text: "El pressupost inicial és de deu mil." }] }],
            summary: null,
          },
        ],
      },
    }),
  );
  await page.goto(`/brain/timeline/${CONCEPT}`);
  await expect(page.getByRole("heading", { name: /Línea de tiempo: Pressupost/ })).toBeVisible();
  const entries = page.getByTestId("timeline").locator(":scope > li");
  await expect(entries).toHaveCount(2);
  await expect(entries.nth(0)).toContainText("12 de febrero de 2026");
  await expect(entries.nth(1)).toContainText("15 de enero de 2026");
  await expect(entries.nth(1)).toContainText("Decisión Aprovar el pressupost inicial");
  await expect(entries.nth(1).getByRole("link", { name: "01:15" }).first()).toHaveAttribute(
    "href",
    `/meetings/${JAN}?at=75&segment=system-00003&play=1`,
  );
  await expect(entries.nth(0)).toContainText("Acción Enviar el pressupost nou · Marta · divendres");
  await expect(entries.nth(0).getByRole("link", { name: "Apuntes ¶2" })).toHaveAttribute("href", `/meetings/${FEB}?note=note-002`);
});

test("a concept nobody mentions any more says so", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/brain/concepts/gone/timeline", (route) => route.fulfill({ status: 404, json: { detail: "CONCEPT_NOT_FOUND" } }));
  await page.goto("/brain/timeline/gone");
  await expect(page.getByRole("alert")).toContainText("ya no aparece en ninguna reunión");
});
