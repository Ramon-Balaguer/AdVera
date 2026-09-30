import { expect, type Route, test } from "@playwright/test";

// Synthetic data only: no real meeting content (spec §Prohibiciones).
const MEETING_ID = "11111111-1111-4111-8111-111111111111";
const SECONDS = 4;

function wav(seconds: number): Buffer {
  const rate = 16_000;
  const data = Buffer.alloc(seconds * rate * 2);
  for (let i = 0; i < seconds * rate; i++) {
    data.writeInt16LE(Math.round(4000 * Math.sin((2 * Math.PI * 440 * i) / rate)), i * 2);
  }
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

const AUDIO = wav(SECONDS);

function meeting(overrides: Record<string, unknown> = {}) {
  return {
    id: MEETING_ID,
    title: "Reunión sintética",
    description: null,
    status: "scheduled",
    started_at: null,
    ended_at: null,
    duration: null,
    primary_language: [],
    created_by: null,
    created_at: "2026-09-30T10:00:00Z",
    updated_at: "2026-09-30T10:00:00Z",
    attendee_count: null,
    tracks: [],
    ...overrides,
  };
}

function job(status: string, overrides: Record<string, unknown> = {}) {
  return {
    job_id: "job-1",
    meeting_id: MEETING_ID,
    status,
    stage: status === "completed" ? "completed" : "transcribing",
    progress: status === "completed" ? 1 : 0,
    track: null,
    processed_tracks: status === "completed" ? 1 : 0,
    total_tracks: 1,
    attempts: 1,
    max_attempts: 3,
    provider: "whisperx",
    model: "small",
    error: null,
    created_at: "2026-09-30T10:00:00Z",
    started_at: null,
    completed_at: null,
    updated_at: "2026-09-30T10:00:01Z",
    ...overrides,
  };
}

const TRANSCRIPT = {
  meeting_id: MEETING_ID,
  status: "definitive",
  primary_language: ["ca"],
  segments: [
    { id: "system-00000", start: 0.5, end: 1.5, text: "Primer segmento sintético", track: "system", language: "ca", speaker: null },
    { id: "system-00001", start: 2.5, end: 3.5, text: "Segundo segmento sintético", track: "system", language: "ca", speaker: null },
  ],
};

function serveAudio(route: Route) {
  const range = route.request().headers()["range"];
  const total = AUDIO.length;
  if (!range) {
    return route.fulfill({
      status: 200,
      body: AUDIO,
      headers: { "Content-Type": "audio/wav", "Accept-Ranges": "bytes", "Content-Length": String(total) },
    });
  }
  const [startText, endText] = range.replace("bytes=", "").split("-");
  const start = Number(startText);
  const end = endText ? Math.min(Number(endText), total - 1) : total - 1;
  return route.fulfill({
    status: 206,
    body: AUDIO.subarray(start, end + 1),
    headers: {
      "Content-Type": "audio/wav",
      "Accept-Ranges": "bytes",
      "Content-Range": `bytes ${start}-${end}/${total}`,
      "Content-Length": String(end - start + 1),
    },
  });
}

test("create a meeting, import media and play the definitive transcript from a segment", async ({ page }) => {
  let imported = false;
  let polls = 0;

  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({ json: { available: false, tracks: {} } }),
  );
  await page.route("**/api/meetings/*/brain", (route) =>
    route.fulfill({ json: { meeting_id: "m", state: "blocked", llm_configured: false } }),
  );
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/meetings", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, json: meeting() })
      : route.fulfill({ json: [] }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) => {
    if (!imported) return route.fulfill({ json: meeting() });
    const done = polls >= 2;
    return route.fulfill({
      json: meeting({
        status: done ? "ready" : "processing",
        tracks: ["system"],
        duration: done ? SECONDS : null,
        primary_language: done ? ["ca"] : [],
        attendee_count: done ? 0 : null,
      }),
    });
  });
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) => {
    if (!imported) return route.fulfill({ status: 404, json: { detail: "TRANSCRIPTION_NOT_FOUND" } });
    polls += 1;
    return route.fulfill({ json: job(polls >= 2 ? "completed" : "running") });
  });
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    imported && polls >= 2
      ? route.fulfill({ json: TRANSCRIPT })
      : route.fulfill({ status: 404, json: { detail: "TRANSCRIPT_NOT_AVAILABLE" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/imports`, (route) => {
    imported = true;
    return route.fulfill({
      status: 202,
      json: { meeting: meeting({ status: "processing", tracks: ["system"] }), transcription: job("queued") },
    });
  });
  await page.route(`**/api/meetings/${MEETING_ID}/audio/system`, serveAudio);

  await page.goto("/meetings");
  await page.getByPlaceholder("Título de la nueva reunión").fill("Reunión sintética");
  await page.getByRole("button", { name: "Crear reunión" }).click();
  await expect(page.getByRole("heading", { name: "Reunión sintética" })).toBeVisible();

  await page.getByRole("button", { name: "Importar" }).click();
  const dialog = page.getByRole("dialog", { name: "Importar audio o vídeo" });
  await dialog.getByTestId("import-file").setInputFiles({
    name: "sintetico.wav",
    mimeType: "audio/wav",
    buffer: AUDIO,
  });
  await dialog.getByRole("button", { name: "Importar" }).click();
  await expect(dialog).toBeHidden();

  const second = page.getByRole("button", { name: /Segundo segmento sintético/ });
  await expect(second).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("meeting-status")).toHaveText("Lista");
  await expect(page.getByText("Idioma: ca").first()).toBeVisible();

  const audio = page.getByTestId("audio-system");
  await expect
    .poll(() => audio.evaluate((element: HTMLAudioElement) => element.readyState))
    .toBeGreaterThan(0);
  await second.click();
  await expect
    .poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime))
    .toBeGreaterThanOrEqual(2.5);
  await expect(page.locator("li.active")).toContainText("Segundo segmento sintético");
});

test("an unsupported file shows a retryable error and keeps the meeting", async ({ page }) => {
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({ json: { available: false, tracks: {} } }),
  );
  await page.route("**/api/meetings/*/brain", (route) =>
    route.fulfill({ json: { meeting_id: "m", state: "blocked", llm_configured: false } }),
  );
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) => route.fulfill({ json: meeting() }));
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPTION_NOT_FOUND" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPT_NOT_AVAILABLE" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/imports`, (route) =>
    route.fulfill({ status: 415, json: { detail: "UNSUPPORTED_MEDIA" } }),
  );

  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: "Importar" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByTestId("import-file").setInputFiles({
    name: "notas.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("no es audio"),
  });
  await dialog.getByRole("button", { name: "Importar" }).click();
  await expect(dialog.getByRole("alert")).toHaveText(/Formato no soportado/);
  await expect(dialog.getByRole("button", { name: "Reintentar" })).toBeEnabled();
});
