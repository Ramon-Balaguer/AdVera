import { expect, type Page, test } from "@playwright/test";

// Chromium's fake capture device provides a synthetic tone; the backend is mocked.
const MEETING_ID = "22222222-2222-4222-8222-222222222222";

async function paintedPixels(page: Page, testId: string): Promise<number> {
  return page.getByTestId(testId).evaluate((canvas: HTMLCanvasElement) => {
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let painted = 0;
    for (let i = 3; i < data.length; i += 4) if (data[i] > 0) painted += 1;
    return painted;
  });
}

function meeting(status: string) {
  return {
    id: MEETING_ID,
    title: "Captura sintética",
    description: null,
    status,
    started_at: null,
    ended_at: null,
    duration: null,
    primary_language: [],
    created_by: null,
    created_at: "2026-09-30T10:00:00Z",
    updated_at: "2026-09-30T10:00:00Z",
    attendee_count: null,
    tracks: [],
  };
}

async function mockMeeting(page: Page, statusRef: { value: string }) {
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({ json: { available: false, tracks: {} } }),
  );
  await page.route("**/api/meetings/*/brain", (route) =>
    route.fulfill({ json: { meeting_id: "m", state: "blocked", llm_configured: false } }),
  );
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) => route.fulfill({ json: meeting(statusRef.value) }));
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPTION_NOT_FOUND" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPT_NOT_AVAILABLE" } }),
  );
  await page.route("**/api/meetings", (route) => route.fulfill({ json: [] }));
}

test("records the browser microphone as PCM16 frames and stops into the durable job", async ({ page }) => {
  const status = { value: "scheduled" };
  const commands: Array<Record<string, unknown>> = [];
  const frameSizes: number[] = [];
  await mockMeeting(page, status);
  await page.routeWebSocket(`**/ws/meetings/${MEETING_ID}/audio`, (ws) => {
    let sequence = 0;
    ws.onMessage((message) => {
      if (typeof message === "string") {
        const command = JSON.parse(message);
        commands.push(command);
        if (command.type === "start") {
          status.value = "recording";
          ws.send(JSON.stringify({ type: "audio.ready", session_id: "s-1", resumed: false, next_sequence: 0, tracks: {} }));
        } else if (command.type === "stop") {
          status.value = "processing";
          ws.send(JSON.stringify({ type: "audio.stopped", tracks: { microphone: { frames: sequence, bytes: 0, duration: 1 } } }));
          ws.send(JSON.stringify({ type: "transcript.queued", job_id: "job-1", status: "queued" }));
        }
        return;
      }
      sequence += 1;
      frameSizes.push(message.length);
      ws.send(
        JSON.stringify({
          type: "audio.received",
          sequence,
          track: "microphone",
          track_sequence: sequence,
          tracks: { microphone: { frames: sequence, bytes: sequence * 8192, duration: sequence * 0.256 } },
        }),
      );
    });
  });

  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: "● Grabar micrófono" }).click();
  await expect(page.getByTestId("capture-state")).toHaveText("Grabando");
  await expect.poll(() => frameSizes.length, { timeout: 10_000 }).toBeGreaterThanOrEqual(3);
  await expect(page.getByRole("button", { name: "Importar" })).toBeDisabled();
  // Live waveform of the microphone track, drawn from its RMS levels (fake device tone).
  await expect(page.getByTestId("waveform-microphone")).toBeVisible();
  await expect.poll(() => paintedPixels(page, "waveform-microphone")).toBeGreaterThan(50);

  await page.getByRole("button", { name: "■ Detener" }).click();
  await expect(page.getByTestId("capture-state")).toHaveText("Grabación guardada");
  await expect(page.getByTestId("waveform-microphone")).toHaveCount(0);

  expect(commands[0]).toEqual({ type: "start" });
  expect(commands.at(-1)).toEqual({ type: "stop" });
  // 4096 samples of 16-bit PCM per frame (the final flush may be shorter).
  expect(frameSizes.slice(0, 3)).toEqual([8192, 8192, 8192]);
});

test("reconnects after a dropped socket and resumes with the session cursor", async ({ page }) => {
  const status = { value: "scheduled" };
  const starts: Array<Record<string, unknown>> = [];
  await mockMeeting(page, status);
  let connections = 0;
  await page.routeWebSocket(`**/ws/meetings/${MEETING_ID}/audio`, (ws) => {
    connections += 1;
    const connection = connections;
    let frames = 0;
    ws.onMessage((message) => {
      if (typeof message === "string") {
        const command = JSON.parse(message);
        if (command.type === "start") {
          starts.push(command);
          status.value = "recording";
          const next = connection === 1 ? 0 : 2;
          ws.send(JSON.stringify({ type: "audio.ready", session_id: "s-1", resumed: connection > 1, next_sequence: next, tracks: {} }));
        }
        return;
      }
      frames += 1;
      ws.send(JSON.stringify({ type: "audio.received", sequence: frames, track: "microphone", track_sequence: frames, tracks: {} }));
      if (connection === 1 && frames === 2) ws.close();
    });
  });

  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: "● Grabar micrófono" }).click();
  await expect.poll(() => starts.length, { timeout: 15_000 }).toBe(2);
  expect(starts[1]).toEqual({ type: "start", resume: true, session_id: "s-1", next_sequence: 2 });
  await expect(page.getByTestId("capture-state")).toHaveText("Grabando");
});

test("a meeting that already has audio cannot be recorded again", async ({ page }) => {
  await mockMeeting(page, { value: "ready" });
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) =>
    route.fulfill({ json: { ...meeting("ready"), tracks: ["microphone"] } }),
  );
  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByTestId("already-recorded")).toContainText("crea otra reunión");
  await expect(page.getByRole("button", { name: /Grabar micrófono/ })).toBeDisabled();
});
