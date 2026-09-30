import { expect, test } from "@playwright/test";

// Global Memory Q&A with mocked backend; synthetic data only.
const MEETING_ID = "55555555-5555-4555-8555-555555555555";
const QUERY_ID = "q-1";

function wav(seconds: number): Buffer {
  const rate = 16_000;
  const data = Buffer.alloc(seconds * rate * 2);
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  return Buffer.concat([header, data]);
}
const AUDIO = wav(20);

const SOURCE = {
  meeting_id: MEETING_ID,
  meeting_title: "Sincro semanal",
  meeting_date: "2026-09-30T10:00:00+00:00",
  segment_id: "system-00002",
  start: 12.4,
  end: 16,
  speaker: "SPEAKER_01",
  language: "es",
  text: "Ampliaremos el volumen de almacenamiento esta semana.",
};

test("ask a question, follow the states and open the cited second of the meeting", async ({ page }) => {
  let posted: Record<string, unknown> | null = null;
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/memory/overview", (route) =>
    route.fulfill({
      json: { state: "ready", meetings_indexed: 3, chunks: 42, embedded_chunks: 42, jobs_pending: 0, jobs_failed: 0, llm_configured: true },
    }),
  );
  await page.route("**/api/memory/query", (route) => {
    posted = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: { query_id: QUERY_ID, query: "q", status: "queued", error: null, result: null } });
  });
  await page.routeWebSocket(`**/ws/query/${QUERY_ID}`, (ws) => {
    const state = (status: string, result: unknown = null) =>
      ws.send(JSON.stringify({ type: "query.state", query_id: QUERY_ID, query: "q", status, error: null, result }));
    state("retrieving");
    setTimeout(() => state("synthesizing"), 150);
    setTimeout(
      () =>
        state("completed", {
          answer: "Se decidió ampliar el volumen de almacenamiento esta semana.",
          sources: [SOURCE],
          retrieval: "hybrid",
          retrieved: [],
        }),
      300,
    );
  });
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) =>
    route.fulfill({
      json: {
        id: MEETING_ID, title: "Sincro semanal", description: null, status: "ready", started_at: null, ended_at: null,
        duration: 20, primary_language: ["es"], created_by: null, created_at: "2026-09-30T10:00:00Z",
        updated_at: "2026-09-30T10:00:00Z", attendee_count: 2, tracks: ["system"],
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) => route.fulfill({ status: 404, json: {} }));
  await page.route(`**/api/meetings/${MEETING_ID}/brain`, (route) =>
    route.fulfill({ json: { meeting_id: MEETING_ID, state: "not_started", llm_configured: true } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    route.fulfill({
      json: {
        meeting_id: MEETING_ID, status: "definitive", primary_language: ["es"],
        segments: [
          { id: "system-00001", start: 2, end: 6, text: "Las copias fallan.", track: "system", language: "es", speaker: "SPEAKER_00" },
          { id: "system-00002", start: 12.4, end: 16, text: SOURCE.text, track: "system", language: "es", speaker: "SPEAKER_01" },
        ],
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/audio/system`, (route) =>
    route.fulfill({ status: 200, body: AUDIO, headers: { "Content-Type": "audio/wav", "Accept-Ranges": "bytes" } }),
  );

  await page.goto("/memory");
  await expect(page.getByTestId("memory-overview")).toContainText("3 reuniones indexadas");
  await page.getByLabel("¿Qué quieres saber de tus reuniones?").fill("¿Qué decidimos sobre el almacenamiento?");
  await page.getByRole("combobox").first().selectOption("es");
  await page.getByLabel("¿Qué quieres saber de tus reuniones?").press("Control+Enter");

  const answer = page.getByTestId("memory-answer");
  await expect(answer).toContainText("Se decidió ampliar el volumen", { timeout: 10_000 });
  expect(posted).toEqual({ query: "¿Qué decidimos sobre el almacenamiento?", filters: { language: "es" } });

  await answer.getByRole("link", { name: "Sincro semanal · 00:12" }).click();
  await expect(page).toHaveURL(
    (url) =>
      url.pathname === `/meetings/${MEETING_ID}` &&
      url.searchParams.get("at") === "12" &&
      url.searchParams.get("segment") === "system-00002" &&
      url.searchParams.get("play") === "1",
  );
  await expect(page.locator("li.active")).toContainText(SOURCE.text);
  await expect
    .poll(() => page.getByTestId("audio-system").evaluate((audio: HTMLAudioElement) => audio.currentTime))
    .toBe(12);
  // The reference starts playing on its own.
  await expect
    .poll(() => page.getByTestId("audio-system").evaluate((audio: HTMLAudioElement) => !audio.paused))
    .toBe(true);

  // Going back restores the search pre-filled, with the summary and the references.
  await page.goBack();
  await expect(page.getByLabel("¿Qué quieres saber de tus reuniones?")).toHaveValue("¿Qué decidimos sobre el almacenamiento?");
  await expect(page.getByRole("combobox").first()).toHaveValue("es");
  await expect(page.getByTestId("memory-answer")).toContainText("Se decidió ampliar el volumen");
  await expect(page.getByTestId("memory-answer").getByRole("link", { name: "Sincro semanal · 00:12" })).toBeVisible();

  // ...and it survives a full reload of the client.
  await page.reload();
  await expect(page.getByTestId("memory-answer")).toContainText("Se decidió ampliar el volumen");
});

test("no evidence is stated plainly and the LLM must be configured", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/memory/overview", (route) =>
    route.fulfill({ json: { state: "empty", meetings_indexed: 0, chunks: 0, embedded_chunks: 0, jobs_pending: 0, jobs_failed: 0, llm_configured: false } }),
  );
  await page.route("**/api/memory/query", (route) => route.fulfill({ status: 409, json: { detail: "LLM_NOT_CONFIGURED" } }));
  await page.goto("/memory");
  await expect(page.getByTestId("memory-overview")).toContainText("Todavía no hay reuniones indexadas.");
  await page.getByLabel("¿Qué quieres saber de tus reuniones?").fill("¿Algo?");
  await page.getByRole("button", { name: "Preguntar" }).click();
  await expect(page.getByRole("alert")).toContainText("Configura el servidor y el modelo LLM");
  await expect(page.getByRole("link", { name: "Ir a Ajustes" })).toBeVisible();
});


test("fragments found without an answer are shown like sources, as links that play", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/memory/overview", (route) =>
    route.fulfill({
      json: { state: "ready", meetings_indexed: 1, chunks: 4, embedded_chunks: 4, jobs_pending: 0, jobs_failed: 0, llm_configured: true },
    }),
  );
  await page.route("**/api/memory/query", (route) =>
    route.fulfill({
      status: 202,
      json: {
        query_id: QUERY_ID, query: "q", status: "empty", error: null,
        result: {
          answer: null, sources: [], retrieval: "hybrid",
          retrieved: [
            {
              meeting_id: MEETING_ID, meeting_title: "Sincro semanal", start: 12.4, segment_id: "system-00002",
              speaker: "SPEAKER_01", language: "ca", content: "Jo proposaria publicar-la el dilluns vinent.",
            },
            // A run saved before the text was kept: still listed, just not a link.
            { meeting_id: MEETING_ID, meeting_title: "Altra reunió", start: 3 },
          ],
        },
      },
    }),
  );
  await page.goto("/memory");
  await page.getByLabel("¿Qué quieres saber de tus reuniones?").fill("¿Quién publica el lunes?");
  await page.getByRole("button", { name: "Preguntar" }).click();

  await expect(page.getByTestId("memory-status")).toContainText("No hay evidencia suficiente");
  const found = page.getByTestId("memory-retrieved");
  await expect(found).toContainText("Fragmentos encontrados");
  // The same structure as the sources: link with meeting and time, speaker and language, quote.
  const link = found.getByRole("link", { name: "Sincro semanal · 00:12" });
  await expect(link).toHaveAttribute("href", /segment=system-00002/);
  await expect(link).toHaveAttribute("href", /at=12/);
  await expect(link).toHaveAttribute("href", /play=1/);
  await expect(found).toContainText("SPEAKER_01 · ca");
  await expect(found.getByText("Jo proposaria publicar-la el dilluns vinent.")).toBeVisible();
  await expect(found.getByRole("link")).toHaveCount(1);
  await expect(found).toContainText("Altra reunió · 00:03");
});


for (const [reason, text] of [
  ["NO_MATCH", "no encontró ningún fragmento"],
  ["MODEL_INSUFFICIENT", "consideró que no contienen la respuesta"],
  ["UNCITED", "sin citar fragmentos válidos"],
  ["NO_SEGMENTS", "ya no están en la transcripción definitiva"],
] as Array<[string, string]>) {
  test(`an empty result says why (${reason})`, async ({ page }) => {
    await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
    await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
    await page.route("**/api/memory/overview", (route) =>
      route.fulfill({
        json: { state: "ready", meetings_indexed: 1, chunks: 4, embedded_chunks: 4, jobs_pending: 0, jobs_failed: 0, llm_configured: true },
      }),
    );
    await page.route("**/api/memory/query", (route) =>
      route.fulfill({
        status: 202,
        json: {
          query_id: QUERY_ID, query: "q", status: "empty", error: null,
          result: { answer: null, sources: [], retrieval: "hybrid", retrieved: [], reason },
        },
      }),
    );
    await page.goto("/memory");
    await page.getByLabel("¿Qué quieres saber de tus reuniones?").fill("¿Qué se decidió?");
    await page.getByRole("button", { name: "Preguntar" }).click();
    await expect(page.getByTestId("memory-status")).toContainText("No hay evidencia suficiente");
    await expect(page.getByTestId("memory-reason")).toContainText(text);
  });
}
