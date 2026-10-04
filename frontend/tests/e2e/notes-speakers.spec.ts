import { expect, type Page, test } from "./fixtures";

// Notes with @references (ADR 0020) and speakers named as people (ADR 0021); backend mocked.
const MEETING_ID = "12121212-1212-4121-8121-121212121212";
const GUILLEM_ID = "34343434-3434-4343-8343-343434343434";

const SEGMENTS = [
  { id: "system-00000", start: 2, end: 5, text: "Revisem el pla de còpies.", track: "system", language: "ca", speaker: "SPEAKER_00", person: null },
  { id: "system-00001", start: 6, end: 9, text: "Jo porto l'inventari.", track: "system", language: "ca", speaker: "SPEAKER_01", person: null },
];
const GUILLEM_SEGMENTS = [
  { id: "system-00000", start: 0, end: 4, text: "Hola a tothom.", track: "system", language: "ca", speaker: "SPEAKER_00", person: "Ramón" },
  { id: "system-00001", start: 750, end: 754, text: "El proveïdor puja els preus al gener.", track: "system", language: "ca", speaker: "SPEAKER_01", person: null },
];

function meeting(id: string, title: string) {
  return {
    id, title, description: null, status: "ready", started_at: null, ended_at: null, duration: 30,
    primary_language: ["ca"], created_by: null, created_at: "2026-09-30T10:00:00Z",
    updated_at: "2026-09-30T10:00:00Z", attendee_count: 2, tracks: [], tags: [],
  };
}

interface State {
  notes: string;
  savedNotes: string[];
  savedSpeakers: unknown[];
  summary?: unknown;
}

async function mock(page: Page, state: State) {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/meetings", (route) =>
    route.fulfill({ json: [meeting(MEETING_ID, "Seguiment"), meeting(GUILLEM_ID, "Meet de Guillem")] }),
  );
  for (const [id, title, segments] of [
    [MEETING_ID, "Seguiment", SEGMENTS],
    [GUILLEM_ID, "Meet de Guillem", GUILLEM_SEGMENTS],
  ] as const) {
    await page.route(`**/api/meetings/${id}`, (route) => route.fulfill({ json: meeting(id, title) }));
    await page.route(`**/api/meetings/${id}/transcript`, (route) =>
      route.fulfill({
        json: { meeting_id: id, status: "definitive", primary_language: ["ca"], segments },
      }),
    );
    await page.route(`**/api/meetings/${id}/transcription`, (route) => route.fulfill({ status: 404, json: {} }));
    await page.route(`**/api/meetings/${id}/references`, (route) => route.fulfill({ json: [] }));
  }
  await page.route(`**/api/meetings/${MEETING_ID}/summary`, (route) =>
    route.fulfill({ json: state.summary ?? { meeting_id: MEETING_ID, state: "blocked", llm_configured: false } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/notes`, (route) => {
    if (route.request().method() === "PUT") {
      state.notes = route.request().postDataJSON().content;
      state.savedNotes.push(state.notes);
      return route.fulfill({
        json: { meeting_id: MEETING_ID, content: state.notes, updated_at: "2026-10-01T10:00:00Z", analysis: "queued" },
      });
    }
    return route.fulfill({ json: { meeting_id: MEETING_ID, content: state.notes, updated_at: null } });
  });
  await page.route("**/api/people", (route) =>
    route.fulfill({ json: [{ concept_id: "p1", name: "Ramón", meetings: 3 }, { concept_id: "p2", name: "Núria", meetings: 1 }] }),
  );
  const speakers = (names: Record<string, string | null>) => ({
    speakers: [
      { track: "system", speaker: "SPEAKER_00", seconds: 3, segments: 1, sample: "Revisem el pla", person: names.SPEAKER_00 ?? null, concept_id: null },
      { track: "system", speaker: "SPEAKER_01", seconds: 3, segments: 1, sample: "Jo porto", person: names.SPEAKER_01 ?? null, concept_id: null },
    ],
  });
  await page.route(`**/api/meetings/${MEETING_ID}/speakers`, (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      state.savedSpeakers.push(body);
      const names = Object.fromEntries(body.assignments.map((a: { speaker: string; person: string | null }) => [a.speaker, a.person]));
      return route.fulfill({ json: { ...speakers(names), analysis: "queued" } });
    }
    return route.fulfill({ json: speakers({}) });
  });
}

const editor = (page: Page) => page.getByTestId("notes-editor").locator(".cm-content");

test("notes show their formatting while typing, grey signs while editing, and hide them after saving", async ({ page }) => {
  const state: State = { notes: "", savedNotes: [], savedSpeakers: [] };
  await mock(page, state);
  await page.goto(`/meetings/${MEETING_ID}`);

  await editor(page).click();
  await page.keyboard.type("# Pla de còpies");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Cal **renegociar** i ~~ajornar~~.");

  const heading = editor(page).locator(".cm-line").first();
  // The heading is big while its "#" stays visible in grey.
  await expect(heading).toContainText("# Pla de còpies");
  const sizes = await heading.evaluate((line) => {
    const spans = [...line.querySelectorAll("span")];
    const title = spans.find((span) => span.textContent?.includes("Pla"))!;
    const mark = spans.find((span) => span.textContent?.trim() === "#")!;
    return { title: parseFloat(getComputedStyle(title).fontSize), mark: getComputedStyle(mark).color };
  });
  expect(sizes.title).toBeGreaterThan(20);
  expect(sizes.mark).toBe("rgb(156, 163, 175)");
  const bold = editor(page).locator("span", { hasText: /^renegociar$/ });
  await expect(bold).toHaveCSS("font-weight", "700");
  await expect(page.getByText("Cambios sin guardar.")).toBeVisible();

  await page.getByRole("region", { name: "Apuntes" }).getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByRole("status").filter({ hasText: "puesto en cola" })).toBeVisible();
  expect(state.savedNotes).toEqual(["# Pla de còpies\nCal **renegociar** i ~~ajornar~~."]);
  // Not editing any more: the signs are hidden, the text reads clean.
  await expect(heading).toHaveText("Pla de còpies");
  await expect(editor(page).locator(".cm-line").nth(1)).toHaveText("Cal renegociar i ajornar.");
});

test("@ references another meeting, and : one of its segments, as chips stored as links", async ({ page }) => {
  const state: State = { notes: "", savedNotes: [], savedSpeakers: [] };
  await mock(page, state);
  await page.goto(`/meetings/${MEETING_ID}`);

  await editor(page).click();
  await page.keyboard.type("Veure @guill");
  const options = page.locator(".cm-tooltip-autocomplete li");
  await expect(options.first()).toContainText("Meet de Guillem");
  await expect(options).toHaveCount(1); // the meeting itself is not offered
  // CodeMirror ignores Enter for a moment after the list opens, so a quick key is not taken.
  await page.waitForTimeout(150);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("note-reference")).toHaveText("@Meet de Guillem");

  // ":" right after it searches that meeting's segments, by number, time or words.
  await page.keyboard.type(":preus");
  await expect(options.first()).toContainText("#2 · 12:30 · SPEAKER_01");
  await page.waitForTimeout(150);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("note-reference")).toHaveText("@Meet de Guillem · 12:30");

  await page.getByRole("region", { name: "Apuntes" }).getByRole("button", { name: "Guardar" }).click();
  await expect.poll(() => state.savedNotes.length).toBe(1);
  expect(state.savedNotes[0]).toBe(`Veure [@Meet de Guillem · 12:30](/meetings/${GUILLEM_ID}?segment=system-00001)`);
});

test("a note cited by Summary links to the notes", async ({ page }) => {
  const state: State = {
    notes: "Primer apunt.\n\nSegon apunt.",
    savedNotes: [],
    savedSpeakers: [],
    summary: {
      meeting_id: MEETING_ID, state: "completed", llm_configured: true,
      job: { status: "completed", model: "m", language: "es", error: null, attempts: 1 },
      generated_at: "2026-10-01T10:00:00Z",
      result: {
        language: "es",
        summary: { text: "Resumen.", evidence: [{ segment_id: "note-002", start: null, end: null, speaker: null, track: "notes" }] },
        topics: [], decisions: [], actions: [], open_questions: [], risks: [], concepts: [], relationships: [], dropped_items: 0,
      },
    },
  };
  await mock(page, state);
  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: "Apuntes ¶2" }).click();
  await expect(page).toHaveURL(/\?note=note-002/);
});

test("speakers are named with people offered while typing, and saved together", async ({ page }) => {
  const state: State = { notes: "", savedNotes: [], savedSpeakers: [] };
  await mock(page, state);
  await page.goto(`/meetings/${MEETING_ID}`);

  const first = page.getByRole("combobox", { name: "Persona de SPEAKER_00 (Sistema)" });
  await first.fill("ram");
  await page.getByRole("listbox", { name: "Personas conocidas" }).getByRole("option", { name: /Ramón/ }).click();
  await expect(first).toHaveValue("Ramón");
  await page.getByRole("combobox", { name: "Persona de SPEAKER_01 (Sistema)" }).fill("Marta Vidal");

  await page.getByRole("region", { name: "Hablantes" }).getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByRole("status").filter({ hasText: "volverá a analizar" })).toBeVisible();
  expect(state.savedSpeakers).toEqual([
    {
      assignments: [
        { track: "system", speaker: "SPEAKER_00", person: "Ramón" },
        { track: "system", speaker: "SPEAKER_01", person: "Marta Vidal" },
      ],
    },
  ]);
});

test("note blocks split exactly as the backend does", async () => {
  // Same cases as backend/tests/test_notes.py: a cited note-00N is the same block on both sides.
  const fs = await import("node:fs");
  const { noteBlocks } = await import("../../src/features/notes/blocks");
  const cases = JSON.parse(fs.readFileSync(new URL("../fixtures/note-blocks.json", import.meta.url), "utf-8"));
  for (const item of cases as { name: string; markdown: string; blocks: string[] }[]) {
    const markdown = item.markdown.replace(/\r/g, ""); // a CodeMirror document never holds "\r"
    const blocks = noteBlocks(markdown).map((block) =>
      markdown.slice(block.from, block.to).replace(/\n[ \t\f\v]*\n/g, "\n"),
    );
    expect(blocks, item.name).toEqual(item.blocks);
  }
});

test("text typed while saving is kept, and ':' followed by a space is prose", async ({ page }) => {
  const state: State = { notes: "", savedNotes: [], savedSpeakers: [] };
  await mock(page, state);
  let release: () => void = () => undefined;
  await page.route(`**/api/meetings/${MEETING_ID}/notes`, async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    await new Promise<void>((resolve) => (release = resolve));
    const content = route.request().postDataJSON().content;
    state.savedNotes.push(content);
    return route.fulfill({ json: { meeting_id: MEETING_ID, content, updated_at: "2026-10-01T10:00:00Z", analysis: "queued" } });
  });
  await page.goto(`/meetings/${MEETING_ID}`);
  await editor(page).click();
  await page.keyboard.type("Primera línia.");
  await page.getByRole("region", { name: "Apuntes" }).getByRole("button", { name: "Guardar" }).click();
  await editor(page).click(); // back to the editor while the save is still on its way
  await page.keyboard.press("End");
  await page.keyboard.type(" Segona.");
  release();
  await expect(page.getByRole("status").filter({ hasText: "puesto en cola" })).toBeVisible();
  await expect(editor(page)).toContainText("Primera línia. Segona.");
  await expect(page.getByText("Cambios sin guardar.")).toBeVisible();
  expect(state.savedNotes).toEqual(["Primera línia."]);

  await page.keyboard.press("Enter");
  await page.keyboard.type("@guill");
  await page.waitForTimeout(150);
  await page.keyboard.press("Enter");
  await page.keyboard.type(": decidim");
  await expect(page.locator(".cm-tooltip-autocomplete")).toHaveCount(0);
  await page.keyboard.press("Enter");
  await expect(editor(page)).toContainText(": decidim");
});
