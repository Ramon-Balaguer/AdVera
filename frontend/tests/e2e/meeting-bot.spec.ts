import { expect, type Page, test } from "./fixtures";

// Meeting bot (ADR 0026): the page sends a self-hosted Vexa bot to a Google Meet or Teams call,
// follows its status while it owns the meeting, makes it leave, and then shows the call's chat
// (ADR 0027). The API is mocked; tests/e2e-live drives the real thing against real calls.
const MEETING_ID = "44444444-4444-4444-8444-444444444444";

type Bot = {
  id: string;
  meeting_id: string;
  provider: string;
  platform: "google_meet" | "teams";
  meet_url: string;
  bot_name: string;
  status: string;
  consent_notice: "pending" | "sent" | "unsupported";
  error: string | null;
  active: boolean;
  joined_at: string | null;
  left_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

function meeting(status: string, tracks: string[] = []) {
  return {
    id: MEETING_ID,
    title: "Llamada con el bot",
    description: null,
    status,
    started_at: null,
    ended_at: null,
    duration: null,
    primary_language: [],
    created_by: null,
    created_at: "2026-10-16T10:00:00Z",
    updated_at: "2026-10-16T10:00:00Z",
    attendee_count: null,
    tracks,
  };
}

function bot(platform: Bot["platform"], meetUrl: string, status = "requested"): Bot {
  return {
    id: "bot-1",
    meeting_id: MEETING_ID,
    provider: "vexa",
    platform,
    meet_url: meetUrl,
    bot_name: "AdVera Notekeeper",
    status,
    consent_notice: "pending",
    error: null,
    active: true,
    joined_at: null,
    left_at: null,
    completed_at: null,
    created_at: "2026-10-16T10:00:00Z",
    updated_at: "2026-10-16T10:00:00Z",
  };
}

const CHAT = [
  { id: "chat-001", sender: "Marta Prueba", text: "Os paso el enlace del presupuesto", sent_at: null, offset_s: 1.5 },
  { id: "chat-002", sender: "Ramón Prueba", text: "Gràcies!", sent_at: null, offset_s: 3.8 },
];

/** The meeting page around a mutable server state; returns what the page sent. */
async function mockServer(page: Page, state: { meeting: ReturnType<typeof meeting>; bot: Bot | null; configured?: boolean }) {
  const sent: { start: unknown[]; stops: number } = { start: [], stops: 0 };
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/meeting-bot/capabilities", (route) =>
    route.fulfill({
      json:
        state.configured === false
          ? { configured: false, available: false, bot_name: null, platforms: [] }
          : { configured: true, available: true, bot_name: "AdVera Notekeeper", platforms: ["google_meet", "teams"] },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/*`, (route) => route.fulfill({ status: 404, json: { detail: "NOT_FOUND" } }));
  await page.route("**/api/meetings/*/summary", (route) =>
    route.fulfill({ json: { meeting_id: MEETING_ID, state: "blocked", llm_configured: false } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) => route.fulfill({ json: state.meeting }));
  await page.route(`**/api/meetings/${MEETING_ID}/chat`, (route) => route.fulfill({ json: CHAT }));
  await page.route(`**/api/meetings/${MEETING_ID}/bot`, async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      const body = route.request().postDataJSON() as { meet_url: string };
      sent.start.push(body);
      if (!body.meet_url.includes("meet.google.com") && !body.meet_url.includes("teams.")) {
        return route.fulfill({ status: 400, json: { detail: "INVALID_MEET_URL" } });
      }
      const teams = body.meet_url.includes("teams.");
      state.bot = bot(teams ? "teams" : "google_meet", body.meet_url.split("?")[0]);
      state.meeting = meeting("recording");
      return route.fulfill({ status: 201, json: state.bot });
    }
    if (method === "DELETE") {
      sent.stops += 1;
      state.bot = { ...state.bot!, status: "stopping" };
      return route.fulfill({ json: state.bot });
    }
    return state.bot ? route.fulfill({ json: state.bot }) : route.fulfill({ status: 404, json: { detail: "BOT_NOT_FOUND" } });
  });
  return sent;
}

test("sends the bot to a Google Meet call, follows it and makes it leave", async ({ page }) => {
  const state = { meeting: meeting("scheduled"), bot: null as Bot | null };
  const sent = await mockServer(page, state);

  await page.goto(`/meetings/${MEETING_ID}`);
  const send = page.getByRole("button", { name: "Enviar AdVera Notekeeper a Google Meet o Teams" });
  await expect(send).toBeEnabled();
  // The brand is written as is, never upper-cased by CSS.
  await expect(send).toHaveCSS("text-transform", "none");
  await send.click();
  await page.getByLabel("Enlace de la reunión de Google Meet o Teams").fill("https://meet.google.com/abc-defg-hij");
  await page.getByRole("button", { name: "Enviar bot" }).click();

  expect(sent.start).toEqual([{ meet_url: "https://meet.google.com/abc-defg-hij" }]);
  await expect(page.getByTestId("bot-state")).toHaveText("AdVera Notekeeper en Google Meet · en camino…");
  // The bot owns the meeting: no microphone, no "interrupted recording" offer.
  await expect(page.getByRole("button", { name: /Grabar micrófono/ })).toHaveCount(0);
  await expect(page.getByText("Hay una grabación interrumpida")).toHaveCount(0);

  state.bot = { ...state.bot!, status: "awaiting_admission" };
  await expect(page.getByTestId("bot-state")).toContainText("esperando a que lo admitan en la llamada");

  state.bot = { ...state.bot!, status: "active", consent_notice: "unsupported", joined_at: "2026-10-16T10:00:01Z" };
  await expect(page.getByTestId("bot-state")).toContainText("en la llamada, grabando");
  await expect(page.getByTestId("bot-consent")).toContainText("Avisa a los participantes");

  await page.getByRole("button", { name: "Sacar bot" }).click();
  expect(sent.stops).toBe(1);
  await expect(page.getByTestId("bot-state")).toContainText("saliendo de la llamada…");
  await expect(page.getByRole("button", { name: "Sacar bot" })).toHaveCount(0);

  // Vexa hands the recording over: the meeting has a system track and is transcribed.
  state.bot = { ...state.bot!, status: "ingesting" };
  await expect(page.getByTestId("bot-state")).toContainText("procesando la grabación…");
  state.bot = { ...state.bot!, status: "completed", active: false };
  state.meeting = meeting("processing", ["system"]);
  await expect(page.getByTestId("bot-state")).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByRole("button", { name: /Enviar AdVera Notekeeper/ })).toHaveCount(0);

  // The call's chat, in its own tab.
  await page.getByRole("tab", { name: "Chat" }).click();
  const messages = page.getByTestId("chat-message");
  await expect(messages).toHaveCount(2);
  await expect(messages.first()).toContainText("Marta Prueba: Os paso el enlace del presupuesto");
  await expect(messages.last()).toContainText("00:03 Ramón Prueba: Gràcies!");
});

test("sends the bot to a Microsoft Teams call with its passcode", async ({ page }) => {
  const state = { meeting: meeting("scheduled"), bot: null as Bot | null };
  const sent = await mockServer(page, state);

  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: "Enviar AdVera Notekeeper a Google Meet o Teams" }).click();
  await page
    .getByLabel("Enlace de la reunión de Google Meet o Teams")
    .fill("https://teams.microsoft.com/meet/3812345678901?p=Ab12Cd");
  await page.getByRole("button", { name: "Enviar bot" }).click();

  expect(sent.start).toEqual([{ meet_url: "https://teams.microsoft.com/meet/3812345678901?p=Ab12Cd" }]);
  await expect(page.getByTestId("bot-state")).toContainText("AdVera Notekeeper en Microsoft Teams");
  state.bot = { ...state.bot!, status: "needs_help" };
  await expect(page.getByTestId("bot-state")).toContainText("necesita ayuda para entrar");
  await expect(page.getByRole("button", { name: "Sacar bot" })).toBeVisible();
});

test("an invalid link is explained and nothing starts", async ({ page }) => {
  const state = { meeting: meeting("scheduled"), bot: null as Bot | null };
  await mockServer(page, state);
  await page.goto(`/meetings/${MEETING_ID}`);
  await page.getByRole("button", { name: /Enviar AdVera Notekeeper/ }).click();
  await page.getByLabel("Enlace de la reunión de Google Meet o Teams").fill("https://zoom.us/j/123456789");
  await page.getByRole("button", { name: "Enviar bot" }).click();
  await expect(page.getByRole("alert")).toHaveText("El enlace no es de una reunión de Google Meet o Teams.");
  await expect(page.getByTestId("bot-state")).toHaveCount(0);
});

test("a bot that failed gives the meeting back to the other sources", async ({ page }) => {
  const failed = { ...bot("google_meet", "https://meet.google.com/abc-defg-hij", "failed"), active: false, error: "BOT_FAILED" };
  await mockServer(page, { meeting: meeting("scheduled"), bot: failed });
  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByRole("alert")).toHaveText("El bot no pudo entrar en la llamada o grabarla.");
  await expect(page.getByRole("button", { name: "● Grabar micrófono" })).toBeEnabled();
  await expect(page.getByRole("button", { name: /Enviar AdVera Notekeeper/ })).toBeEnabled();
});

test("without Vexa configured there is no bot button, and an empty chat says why", async ({ page }) => {
  await mockServer(page, { meeting: meeting("scheduled"), bot: null, configured: false });
  await page.route(`**/api/meetings/${MEETING_ID}/chat`, (route) => route.fulfill({ json: [] }));
  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByRole("button", { name: "● Grabar micrófono" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Enviar AdVera Notekeeper/ })).toHaveCount(0);
  await page.getByRole("tab", { name: "Chat" }).click();
  await expect(page.getByText("Esta reunión no tiene chat.")).toBeVisible();
});

test("Settings store the Vexa connection without reading the key back", async ({ page }) => {
  let put: Record<string, unknown> | null = null;
  const settings = {
    llm_provider: "ollama",
    llm_base_url: "http://ollama:11434",
    llm_model: "m",
    llm_output_language: "es",
    llm_api_key_set: false,
    llm_configured: true,
    setup_completed: true,
    setup_required: false,
    vexa_base_url: "",
    vexa_bot_name: "AdVera Notekeeper",
    vexa_speaker_names: false,
    vexa_api_key_set: false,
    vexa_webhook_secret_set: false,
    vexa_configured: false,
  };
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/settings/models", (route) => route.fulfill({ json: { base_url: "http://ollama:11434", models: ["m"] } }));
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PUT") {
      put = route.request().postDataJSON();
      return route.fulfill({
        json: { ...settings, vexa_base_url: "http://vexa:8056", vexa_api_key_set: true, vexa_webhook_secret_set: true, vexa_configured: true },
      });
    }
    return route.fulfill({ json: settings });
  });
  await page.goto("/settings");
  const form = page.getByRole("form", { name: "Bot de reuniones (Vexa)" });
  await form.getByLabel("URL de Vexa").fill("http://vexa:8056");
  await form.getByLabel("Clave de API de Vexa").fill("vexa-key");
  await form.getByLabel("Secreto del webhook").fill("hook-secret");
  await form.getByRole("button", { name: "Guardar bot" }).click();
  await expect(form.getByRole("status")).toHaveText("Bot de reuniones guardado.");
  expect(put).toEqual({
    vexa_base_url: "http://vexa:8056",
    vexa_bot_name: "AdVera Notekeeper",
    vexa_speaker_names: false,
    vexa_api_key: "vexa-key",
    vexa_webhook_secret: "hook-secret",
  });
  // Write-only: the fields are emptied and only say that something is stored.
  await expect(form.getByLabel("Clave de API de Vexa")).toHaveValue("");
  await expect(form.getByLabel("Clave de API de Vexa")).toHaveAttribute("placeholder", "Guardada. Escribe para reemplazarla");
});
