import { expect, type Page, type Route, test } from "@playwright/test";

// Synchronized multi-track playback (dual-track-playback-live-metrics.md). Synthetic audio.
const MEETING_ID = "66666666-6666-4666-8666-666666666666";

function wav(seconds: number, frequency: number): Buffer {
  const rate = 16_000;
  const data = Buffer.alloc(seconds * rate * 2);
  for (let i = 0; i < seconds * rate; i++) {
    data.writeInt16LE(Math.round(3000 * Math.sin((2 * Math.PI * frequency * i) / rate)), i * 2);
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

const AUDIO = { microphone: wav(30, 220), system: wav(26, 330) };

function serve(track: "microphone" | "system") {
  return (route: Route) => {
    const body = AUDIO[track];
    const range = route.request().headers()["range"];
    const headers = { "Content-Type": "audio/wav", "Accept-Ranges": "bytes" };
    if (!range) return route.fulfill({ status: 200, body, headers: { ...headers, "Content-Length": String(body.length) } });
    const [a, b] = range.replace("bytes=", "").split("-");
    const start = Number(a);
    const end = b ? Math.min(Number(b), body.length - 1) : body.length - 1;
    return route.fulfill({
      status: 206,
      body: body.subarray(start, end + 1),
      headers: { ...headers, "Content-Range": `bytes ${start}-${end}/${body.length}`, "Content-Length": String(end - start + 1) },
    });
  };
}

const TWO_SEGMENTS = [
  { id: "microphone-00000", start: 2, end: 5, text: "Bon dia des del micròfon.", track: "microphone", language: "ca", speaker: "SPEAKER_00" },
  { id: "system-00000", start: 8, end: 12, text: "Hola des del sistema.", track: "system", language: "ca", speaker: "SPEAKER_01" },
];

// One short phrase per second on alternating tracks: taller than the viewport.
const MANY_SEGMENTS = Array.from({ length: 30 }, (_, i) => ({
  id: `seg-${i}`,
  start: i,
  end: i + 0.9,
  text: `Frase número ${i} de la reunió.`,
  track: i % 2 ? "system" : "microphone",
  language: "ca",
  speaker: i % 2 ? "SPEAKER_01" : "SPEAKER_00",
}));

async function mock(page: Page, segments = TWO_SEGMENTS) {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) =>
    route.fulfill({
      json: {
        id: MEETING_ID, title: "Dos pistas", description: null, status: "ready", started_at: null, ended_at: null,
        duration: 30, primary_language: ["ca"], created_by: null, created_at: "2026-09-30T10:00:00Z",
        updated_at: "2026-09-30T10:00:00Z", attendee_count: 2, tracks: ["microphone", "system"],
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) => route.fulfill({ status: 404, json: {} }));
  await page.route(`**/api/meetings/${MEETING_ID}/brain`, (route) =>
    route.fulfill({ json: { meeting_id: MEETING_ID, state: "blocked", llm_configured: false } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    route.fulfill({
      json: {
        meeting_id: MEETING_ID, status: "definitive", primary_language: ["ca"], segments,
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/audio/microphone`, serve("microphone"));
  await page.route(`**/api/meetings/${MEETING_ID}/audio/system`, serve("system"));
}

const state = (page: Page) =>
  page.evaluate(() =>
    Object.fromEntries(
      ["microphone", "system"].map((track) => {
        const el = document.querySelector(`[data-testid=audio-${track}]`) as HTMLAudioElement;
        return [track, { time: el.currentTime, paused: el.paused, muted: el.muted }];
      }),
    ),
  );

test("every track plays, pauses and seeks together and drift is corrected", async ({ page }) => {
  await mock(page);
  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByTestId("player-time")).toContainText("00:30");

  // Clicking a system segment starts BOTH tracks at its second.
  await page.getByRole("button", { name: /Hola des del sistema/ }).click();
  await expect.poll(async () => (await state(page)).microphone.paused).toBe(false);
  let current = await state(page);
  expect(current.system.paused).toBe(false);
  expect(current.microphone.time).toBeGreaterThanOrEqual(8);
  expect(Math.abs(current.microphone.time - current.system.time)).toBeLessThan(0.3);

  // A forced 1.5 s drift on one track is corrected while playing.
  await page.evaluate(() => {
    const el = document.querySelector("[data-testid=audio-system]") as HTMLAudioElement;
    el.currentTime = el.currentTime + 1.5;
  });
  await expect
    .poll(async () => {
      const s = await state(page);
      return Math.abs(s.microphone.time - s.system.time);
    })
    .toBeLessThan(0.3);

  // One transport pauses every track.
  await page.getByRole("button", { name: "Pausar todas las pistas" }).click();
  current = await state(page);
  expect(current.microphone.paused && current.system.paused).toBe(true);

  // The position bar moves every track.
  await page.getByLabel("Posición de la reunión").fill("20");
  current = await state(page);
  expect(current.microphone.time).toBeCloseTo(20, 0);
  expect(current.system.time).toBeCloseTo(20, 0);

  // Muting one track leaves the other audible.
  await page.getByRole("button", { name: "Silenciar Sistema" }).click();
  current = await state(page);
  expect(current.system.muted).toBe(true);
  expect(current.microphone.muted).toBe(false);
});

test("the segment under the playhead is highlighted and kept in view", async ({ page }) => {
  await mock(page, MANY_SEGMENTS);
  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByTestId("player-time")).toContainText("00:30");
  const segment = (i: number) => page.locator(`#segment-seg-${i}`);
  const active = page.locator(".transcript li.active");

  // Playing from phrase 1: the highlight advances with the audio, one phrase at a time.
  await page.getByRole("button", { name: /Frase número 1 de/ }).click();
  await expect(segment(1)).toHaveAttribute("aria-current", "true");
  await expect(segment(3)).toHaveAttribute("aria-current", "true", { timeout: 5000 });
  await expect(active).toHaveCount(1);
  await expect(segment(1)).not.toHaveClass(/active/);

  // A jump far down the meeting highlights that phrase and scrolls it into view.
  await page.getByLabel("Posición de la reunión").fill("25.3");
  await expect(segment(25)).toHaveAttribute("aria-current", "true");
  await expect(segment(25)).toBeInViewport();
  await expect(segment(2)).not.toBeInViewport();

  // With following off, the user reads elsewhere: the highlight keeps moving, the page does not.
  await page.getByRole("button", { name: "Siguiendo la reproducción" }).click();
  await expect(page.getByRole("button", { name: "Seguir la reproducción" })).toHaveAttribute("aria-pressed", "false");
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(segment(27)).toHaveAttribute("aria-current", "true", { timeout: 5000 });
  await expect(segment(27)).not.toBeInViewport();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});
