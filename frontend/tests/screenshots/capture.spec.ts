import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

import * as demo from "./demo-data";

// English screenshots in docs/screenshots/, Spanish ones (SHOTS_LANG=es) in docs/screenshots/es/.
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../docs/screenshots", demo.LANG === "es" ? "es" : "");
const say = (en: string, es: string) => (demo.LANG === "es" ? es : en);
const shot = (name: string) => path.join(OUT, `${name}.png`);

async function mockAll(page: Page) {
  // Anything not answered below is a 404, so no screen waits on a backend that is not there.
  await page.route("**/api/**", (route) => route.fulfill({ status: 404, json: { detail: "NOT_FOUND" } }));
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/settings", (route) =>
    route.fulfill({
      json: {
        llm_provider: "ollama", llm_base_url: "http://llm.lan:11434", llm_model: "qwen3:32b",
        llm_output_language: demo.LANG, llm_configured: true, setup_required: false,
      },
    }),
  );
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/meeting-bot/capabilities", (route) =>
    route.fulfill({ json: { configured: true, available: true, bot_name: "AdVera Notekeeper", platforms: ["google_meet", "teams"] } }),
  );
  await page.route("**/api/meetings", (route) => route.fulfill({ json: demo.MEETINGS }));
  await page.route("**/api/meetings/tags", (route) => route.fulfill({ json: demo.TAGS }));
  await page.route("**/api/people", (route) => route.fulfill({ json: demo.PEOPLE }));

  const L = demo.LAUNCH;
  await page.route(`**/api/meetings/${L}`, (route) => route.fulfill({ json: demo.MEETINGS.find((m) => m.id === L) }));
  await page.route(`**/api/meetings/${L}/transcript`, (route) =>
    route.fulfill({ json: { meeting_id: L, status: "definitive", primary_language: ["en", "es", "ca"], segments: demo.LAUNCH_SEGMENTS } }),
  );
  await page.route(`**/api/meetings/${L}/summary`, (route) => route.fulfill({ json: demo.LAUNCH_SUMMARY }));
  await page.route(`**/api/meetings/${L}/speakers`, (route) => route.fulfill({ json: demo.LAUNCH_SPEAKERS }));
  await page.route(`**/api/meetings/${L}/notes`, (route) =>
    route.fulfill({ json: { meeting_id: L, content: demo.LAUNCH_NOTES, updated_at: "2026-10-15T10:30:00Z" } }),
  );
  await page.route(`**/api/meetings/${L}/references`, (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/meetings/${L}/chat`, (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/meetings/${L}/brain`, (route) => route.fulfill({ json: demo.LAUNCH_BRAIN }));
  for (const [track, seed] of [["microphone", 1], ["system", 2]] as const) {
    const body = demo.wav(180, seed);
    await page.route(`**/api/meetings/${L}/audio/${track}`, (route) =>
      route.fulfill({ status: 200, body, headers: { "Content-Type": "audio/wav", "Accept-Ranges": "bytes" } }),
    );
  }

  await page.route("**/api/brain/overview", (route) => route.fulfill({ json: demo.BRAIN_OVERVIEW }));
  await page.route("**/api/brain/concept-graph**", (route) => route.fulfill({ json: demo.GRAPH }));
  await page.route("**/api/brain/concepts/c-teams", (route) => route.fulfill({ json: demo.TEAMS_DETAIL }));
  await page.route("**/api/brain/concepts/c-pricing/timeline", (route) => route.fulfill({ json: demo.PRICING_TIMELINE }));
  await page.route("**/api/brain/facts**", (route) => route.fulfill({ json: demo.FACTS }));
  await page.route("**/api/brain/query", (route) => route.fulfill({ status: 202, json: demo.BRAIN_ANSWER }));
  await page.route("**/api/brain/query/*", (route) => route.fulfill({ json: demo.BRAIN_ANSWER }));
  await page.routeWebSocket("**/ws/brain/query/*", (ws) => ws.send(JSON.stringify({ type: "query.state", ...demo.BRAIN_ANSWER })));
  await page.route("**/api/monitor", (route) => route.fulfill({ json: demo.MONITOR }));
}

test.beforeEach(async ({ page }) => {
  await mockAll(page);
});

test("meetings", async ({ page }) => {
  await page.goto("/meetings");
  await expect(page.getByRole("link", { name: demo.MEETINGS[1].title })).toBeVisible();
  await page.screenshot({ path: shot("meetings") });
});

test("meeting summary", async ({ page }) => {
  await page.goto(`/meetings/${demo.LAUNCH}`);
  await expect(page.getByTestId("summary-result")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot("meeting") });
});

test("meeting brain", async ({ page }) => {
  await page.goto(`/meetings/${demo.LAUNCH}`);
  await page.getByRole("tab", { name: "Brain" }).click();
  await expect(page.getByTestId("meeting-concepts")).toBeVisible();
  await page.waitForTimeout(300);
  await page.screenshot({ path: shot("meeting-brain") });
});

test("brain answer", async ({ page }) => {
  await page.goto("/brain");
  const box = page.getByLabel(say("What do you want to know about your meetings?", "¿Qué quieres saber de tus reuniones?"));
  await box.fill(demo.BRAIN_QUESTION_SHOWN);
  await box.press("Control+Enter");
  await expect(page.getByTestId("brain-answer")).toContainText(say("Teams support was moved", "El soporte de Teams pasó"), { timeout: 10_000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: shot("brain-answer") });
});

test("concept graph", async ({ page }) => {
  test.setTimeout(90_000); // 500 concepts take a while to lay out
  await page.goto("/brain");
  const graph = page.getByTestId("concept-graph");
  await expect(graph).toHaveAttribute("data-nodes", String(demo.GRAPH.nodes.length), { timeout: 30_000 });
  await page.waitForTimeout(5000); // let the layout settle
  const section = page.locator("section", { has: graph }).last();
  await section.scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  await section.screenshot({ path: shot("concept-graph") });
});

test("timeline", async ({ page }) => {
  await page.goto("/brain/timeline/c-pricing");
  await expect(page.getByTestId("timeline")).toBeVisible();
  await page.screenshot({ path: shot("timeline") });
});

test("facts", async ({ page }) => {
  await page.goto("/brain/facts");
  await expect(page.getByTestId("fact-decision").first()).toBeVisible();
  await page.screenshot({ path: shot("facts") });
});

test("system", async ({ page }) => {
  await page.goto("/system");
  await page.waitForTimeout(1000);
  await page.screenshot({ path: shot("system") });
});

test("recording", async ({ page }) => {
  const id = "a1000000-0000-4000-8000-000000000010";
  const CAPTURE = "c1000000-0000-4000-8000-000000000010";
  const state = { status: "scheduled" };
  const recording = () => ({
    id, title: say("Design review · pricing page", "Revisión de diseño · página de precios"), description: null, status: state.status, started_at: null, ended_at: null,
    duration: null, primary_language: [], created_by: null, created_at: "2026-10-16T17:00:00Z", updated_at: "2026-10-16T17:00:00Z",
    attendee_count: null, tracks: [], tags: [{ assignment_id: "as-r1", concept_id: "tag-Design", label: say("Design", "Diseño") }, { assignment_id: "as-r2", concept_id: "tag-Launch", label: say("Launch", "Lanzamiento") }],
  });
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({
      json: { available: true, agent_id: "agent-1", platform: "windows", tracks: { microphone: { state: "available" }, system: { state: "available" } } },
    }),
  );
  await page.route("**/api/capture-agent/sessions", (route) =>
    route.fulfill({ status: 201, json: { capture_session_id: CAPTURE, meeting_id: id, tracks: ["microphone", "system"], state: "recording" } }),
  );
  await page.route(`**/api/meetings/${id}`, (route) => route.fulfill({ json: recording() }));
  await page.route(`**/api/meetings/${id}/summary`, (route) =>
    route.fulfill({ json: { meeting_id: id, state: "blocked", llm_configured: true } }),
  );
  const notes = (demo.LANG === "es"
    ? [
        "## Página de precios",
        "- Tres planes: **Autoalojado**, **Equipo**, **Gestionado**",
        "- Empezar por *tus datos se quedan en tus máquinas*",
        "- Poner el requisito de GPU junto al plan autoalojado",
        "",
        "## Pendiente",
        "- ¿Descuento anual? Preguntar a Lucas",
      ]
    : [
        "## Pricing page",
        "- Three tiers: **Self-hosted**, **Team**, **Managed**",
        "- Lead with *your data stays on your machines*",
        "- Show the GPU requirement next to the self-hosted tier",
        "",
        "## Open",
        "- Annual discount? Ask Lucas",
      ]
  ).join("\n");
  await page.route(`**/api/meetings/${id}/notes`, (route) =>
    route.fulfill({ json: { meeting_id: id, content: notes, updated_at: "2026-10-16T17:10:00Z" } }),
  );
  await page.route(`**/api/meetings/${id}/references`, (route) => route.fulfill({ json: [] }));
  // Speech-like levels: each track talks in turns, with syllable-rate wobble.
  await page.routeWebSocket(`**/ws/capture-agent/${CAPTURE}/*/levels`, (ws) => {
    const system = ws.url().includes("/system/");
    let t = 0;
    const interval = setInterval(() => {
      t += 0.1;
      const turn = Math.max(0, Math.sin(t * 0.9 + (system ? Math.PI : 0)));
      const level = 0.006 + turn * (0.05 + 0.17 * Math.abs(Math.sin(t * 7.3)) * Math.abs(Math.sin(t * 2.1 + (system ? 1 : 0))));
      ws.send(JSON.stringify({ type: "levels", level }));
    }, 50);
    ws.onClose(() => clearInterval(interval));
  });
  await page.routeWebSocket(`**/ws/meetings/${id}/audio`, (ws) => {
    let frames = 2930; // about 12.5 minutes in
    ws.onMessage((message) => {
      if (typeof message !== "string" || JSON.parse(message).type !== "start") return;
      state.status = "recording";
      ws.send(JSON.stringify({ type: "audio.ready", session_id: "s-1", resumed: false, next_sequence: 0, tracks: {} }));
      setInterval(() => {
        frames += 1;
        ws.send(
          JSON.stringify({
            type: "audio.received",
            track: frames % 2 ? "microphone" : "system",
            tracks: {
              microphone: { frames, bytes: frames * 8192, duration: frames * 0.256 },
              system: { frames, bytes: frames * 8192, duration: frames * 0.256 },
            },
          }),
        );
      }, 256);
    });
  });

  await page.goto(`/meetings/${id}`);
  await page.getByRole("button", { name: demo.LANG === "es" ? /Grabar con el agente/ : /Record with the agent/ }).click();
  await expect(page.getByTestId("waveform-system")).toBeVisible();
  await page.waitForTimeout(7000); // let both waveforms fill
  await page.screenshot({ path: shot("recording") });
});
