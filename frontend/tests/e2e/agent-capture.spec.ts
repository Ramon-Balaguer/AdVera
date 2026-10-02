import { expect, type Page, test } from "./fixtures";

// Desktop agent mode (ADR 0010): the frontend never carries PCM; it only starts the agent
// through the backend and renders lifecycle events, per-track metrics and levels.
const MEETING_ID = "33333333-3333-4333-8333-333333333333";
const CAPTURE_ID = "capture-1";

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
    title: "Agente sintético",
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

test("records microphone and system tracks through the desktop agent", async ({ page }) => {
  const state = { status: "scheduled" };
  const commands: Array<Record<string, unknown>> = [];
  let sessionRequest: Record<string, unknown> | null = null;
  let binaryFromBrowser = 0;

  await page.route("**/api/meetings/*/brain", (route) =>
    route.fulfill({ json: { meeting_id: "m", state: "blocked", llm_configured: false } }),
  );
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({
      json: {
        available: true,
        agent_id: "agent-1",
        platform: "windows",
        tracks: { microphone: { state: "available" }, system: { state: "available" } },
      },
    }),
  );
  await page.route("**/api/capture-agent/sessions", (route) => {
    sessionRequest = route.request().postDataJSON();
    return route.fulfill({
      status: 201,
      json: { capture_session_id: CAPTURE_ID, meeting_id: MEETING_ID, tracks: ["microphone", "system"], state: "recording" },
    });
  });
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) => route.fulfill({ json: meeting(state.status) }));
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPTION_NOT_FOUND" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPT_NOT_AVAILABLE" } }),
  );

  await page.routeWebSocket(`**/ws/capture-agent/${CAPTURE_ID}/*/levels`, (ws) => {
    const interval = setInterval(() => ws.send(JSON.stringify({ type: "levels", level: 0.2 })), 100);
    ws.onClose(() => clearInterval(interval));
  });
  await page.routeWebSocket(`**/ws/meetings/${MEETING_ID}/audio`, (ws) => {
    let timer: ReturnType<typeof setInterval> | undefined;
    let frames = 0;
    ws.onMessage((message) => {
      if (typeof message !== "string") {
        binaryFromBrowser += 1;
        return;
      }
      const command = JSON.parse(message);
      commands.push(command);
      if (command.type === "start") {
        state.status = "recording";
        ws.send(JSON.stringify({ type: "audio.ready", session_id: "s-1", resumed: false, next_sequence: 0, tracks: {} }));
        // The backend relays the agent's per-track metrics to the meeting socket.
        timer = setInterval(() => {
          frames += 1;
          ws.send(
            JSON.stringify({
              type: "audio.received",
              track: frames % 2 ? "microphone" : "system",
              tracks: {
                microphone: { frames, bytes: frames * 8192, duration: frames * 0.256 },
                system: { frames, bytes: frames * 4096, duration: frames * 0.256 },
              },
            }),
          );
        }, 100);
      } else if (command.type === "stop") {
        clearInterval(timer);
        state.status = "processing";
        ws.send(JSON.stringify({ type: "audio.stopped", tracks: {} }));
        ws.send(JSON.stringify({ type: "transcript.queued", job_id: "job-1", status: "queued" }));
      }
    });
  });

  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: /Grabar con el agente \(micrófono \+ sistema\)/ }).click();
  await expect(page.getByTestId("capture-state")).toHaveText("Grabando");
  expect(commands[0]).toEqual({ type: "start", source: "agent" });
  expect(sessionRequest).toEqual({ meeting_id: MEETING_ID, tracks: ["microphone", "system"] });

  await expect(page.getByTestId("agent-bytes-microphone")).not.toHaveText("0 KiB");
  await expect(page.getByTestId("agent-bytes-system")).not.toHaveText("0 KiB");
  // One live waveform per recorded track, drawn from the agent's per-track levels.
  for (const track of ["microphone", "system"]) {
    await expect(page.getByTestId(`waveform-${track}`)).toBeVisible();
    await expect.poll(() => paintedPixels(page, `waveform-${track}`)).toBeGreaterThan(50);
  }

  await page.getByRole("button", { name: "■ Detener" }).click();
  await expect(page.getByTestId("capture-state")).toHaveText("Grabación guardada");
  await expect(page.getByTestId("waveform-microphone")).toHaveCount(0); // live-only visualization
  await expect(page.getByTestId("waveform-system")).toHaveCount(0);
  expect(commands.at(-1)).toEqual({ type: "stop" });
  expect(binaryFromBrowser).toBe(0); // the browser never transports agent PCM
});

test("falls back to the browser microphone when no agent is connected", async ({ page }) => {
  await page.route("**/api/meetings/*/brain", (route) =>
    route.fulfill({ json: { meeting_id: "m", state: "blocked", llm_configured: false } }),
  );
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({ json: { available: false, tracks: {} } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) => route.fulfill({ json: meeting("scheduled") }));
  await page.route(`**/api/meetings/${MEETING_ID}/*`, (route) =>
    route.fulfill({ status: 404, json: { detail: "NOT_FOUND" } }),
  );
  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByRole("button", { name: "● Grabar micrófono" })).toBeEnabled();
  await expect(page.getByRole("button", { name: /Grabar con el agente/ })).toHaveCount(0);
  await expect(page.getByText("Sin agente de escritorio conectado")).toBeVisible();
});


const AGENT_FAILURES: Array<[string, string]> = [
  ["AGENT_DISCONNECTED", "Se perdió la conexión con el agente"],
  ["TRACK_SEND_FAILED", "El agente perdió la conexión de una pista"],
  ["STORAGE_ERROR", "El servidor no pudo guardar el audio"],
];

for (const [code, message] of AGENT_FAILURES) {
  test(`an agent-side ${code} after recording began is shown and the audio can be finalized`, async ({ page }) => {
  const state = { status: "scheduled" };
  await page.route("**/api/meetings/*/brain", (route) =>
    route.fulfill({ json: { meeting_id: "m", state: "blocked", llm_configured: false } }),
  );
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({
      json: { available: true, agent_id: "agent-1", platform: "windows", tracks: { microphone: { state: "available" } } },
    }),
  );
  await page.route("**/api/capture-agent/sessions", (route) =>
    route.fulfill({
      status: 201,
      json: { capture_session_id: CAPTURE_ID, meeting_id: MEETING_ID, tracks: ["microphone"], state: "recording" },
    }),
  );
  await page.route("**/api/meetings", (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) => route.fulfill({ json: meeting(state.status) }));
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPTION_NOT_FOUND" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPT_NOT_AVAILABLE" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/audio-metrics`, (route) =>
    route.fulfill({
      json: {
        session_id: "s-1",
        capture_session_id: CAPTURE_ID,
        status: "recording",
        next_sequence: 4,
        tracks: { microphone: { frames: 4, bytes: 32768, duration: 1 } },
      },
    }),
  );
  await page.routeWebSocket(`**/ws/capture-agent/${CAPTURE_ID}/*/levels`, () => {});
  await page.routeWebSocket(`**/ws/meetings/${MEETING_ID}/audio`, (ws) => {
    ws.onMessage((message) => {
      if (typeof message !== "string") return;
      const command = JSON.parse(message);
      if (command.type === "start" && !command.resume) {
        state.status = "recording";
        ws.send(JSON.stringify({ type: "audio.ready", session_id: "s-1", resumed: false, next_sequence: 0, tracks: {} }));
        // The agent process dies right after recording began.
        setTimeout(() => ws.send(JSON.stringify({ type: "capture.error", code })), 300);
      }
    });
  });

  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: /Grabar con el agente/ }).click();
  await expect(page.getByTestId("capture-state")).toHaveText("Error de captura");
  await expect(page.getByRole("alert")).toContainText(message);
  // An agent-owned recording is finalized, never "continued" with the browser microphone.
  await expect(page.getByRole("button", { name: "Finalizar grabación" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continuar grabación" })).toHaveCount(0);
});
}
