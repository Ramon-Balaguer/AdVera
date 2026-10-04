import { expect, test } from "./fixtures";

// Synthetic data only. The LLM server and the backend are mocked.
const MEETING_ID = "44444444-4444-4444-8444-444444444444";

test("settings check the Ollama URL, list models and save model and output language", async ({ page }) => {
  let saved: Record<string, unknown> | null = null;
  const current = {
    llm_provider: "ollama",
    llm_base_url: "https://ollama.example.test",
    llm_model: "",
    llm_output_language: "es",
    llm_configured: false,
  };
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PUT") {
      saved = route.request().postDataJSON();
      return route.fulfill({ json: { ...current, ...saved, llm_configured: true } });
    }
    return route.fulfill({ json: current });
  });
  await page.route("**/api/settings/ollama/models", (route) =>
    route.fulfill({ json: { base_url: "https://ollama.example.test", models: ["model-a", "model-b"] } }),
  );

  await page.goto("/settings");
  await expect(page.getByLabel("URL del servidor Ollama")).toHaveValue("https://ollama.example.test");
  // Auto-discovery on load lists the server's models.
  await expect(page.getByText("Conectado: 2 modelos disponibles.")).toBeVisible();
  await page.getByLabel("Modelo").selectOption("model-b");
  await page.getByLabel("Idioma de la interfaz y de las respuestas del resumen y de Brain").selectOption("en");
  await expect(page.getByText("El contenido de los transcripts se envía a este servidor")).toBeVisible();
  await page.getByRole("button", { name: "Guardar" }).click();

  // Saving English switches the whole interface to English at once.
  await expect(page.getByText("Settings saved.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Meetings" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  expect(saved).toEqual({
    llm_base_url: "https://ollama.example.test",
    llm_model: "model-b",
    llm_output_language: "en",
  });
});

test("the interface speaks Catalan when Settings say so", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/settings", (route) =>
    route.fulfill({
      json: { llm_provider: "ollama", llm_base_url: "", llm_model: "", llm_output_language: "ca", llm_configured: false },
    }),
  );
  await page.route("**/api/meetings/tags", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/meetings", (route) => route.fulfill({ json: [] }));
  await page.goto("/meetings");
  await expect(page.getByRole("heading", { name: "Reunions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Crea la reunió" })).toBeVisible();
  await expect(page.getByText("Encara no hi ha reunions.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Configuració" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "ca");
});

test("an unreachable Ollama server is reported without losing the form", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/settings", (route) =>
    route.fulfill({
      json: { llm_provider: "ollama", llm_base_url: "http://down.test", llm_model: "m", llm_output_language: "es", llm_configured: true },
    }),
  );
  await page.route("**/api/settings/ollama/models", (route) =>
    route.fulfill({ status: 502, json: { detail: "OLLAMA_UNREACHABLE" } }),
  );
  await page.goto("/settings");
  await expect(page.getByRole("alert")).toHaveText("No se pudo conectar con el servidor Ollama.");
  await expect(page.getByLabel("Modelo")).toHaveValue("m");
});

test("the Summary panel shows decisions first and a citation seeks the transcript segment", async ({ page }) => {
  let summaryCalls = 0;
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) =>
    route.fulfill({
      json: {
        id: MEETING_ID, title: "Summary sintético", description: null, status: "ready", started_at: null,
        ended_at: null, duration: 20, primary_language: ["ca", "es"], created_by: null,
        created_at: "2026-09-30T10:00:00Z", updated_at: "2026-09-30T10:00:00Z", attendee_count: 2, tracks: [],
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPTION_NOT_FOUND" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) =>
    route.fulfill({
      json: {
        meeting_id: MEETING_ID, status: "definitive", primary_language: ["ca", "es"],
        segments: [
          { id: "system-00000", start: 0, end: 4, text: "Proposem publicar dilluns.", track: "system", language: "ca", speaker: "SPEAKER_00" },
          { id: "system-00001", start: 12, end: 16, text: "De acuerdo, publicamos el lunes.", track: "system", language: "es", speaker: "SPEAKER_01" },
        ],
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/summary`, (route) => {
    summaryCalls += 1;
    if (summaryCalls === 1) {
      return route.fulfill({ json: { meeting_id: MEETING_ID, state: "running", llm_configured: true, job: { status: "running", model: "m", language: "es", error: null, attempts: 1 } } });
    }
    return route.fulfill({
      json: {
        meeting_id: MEETING_ID,
        state: "completed",
        llm_configured: true,
        job: { status: "completed", model: "m", language: "es", error: null, attempts: 1 },
        result: {
          summary: { text: "Se acuerda publicar el lunes.", evidence: [{ segment_id: "system-00001", start: 12, end: 16 }] },
          decisions: [{ text: "Publicar el lunes", state: "decided", evidence: [{ segment_id: "system-00001", start: 12, end: 16 }] }],
          actions: [{ text: "Preparar la nota", owner: "SPEAKER_00", due_date: "viernes", evidence: [{ segment_id: "system-00000", start: 0, end: 4 }] }],
          topics: [], open_questions: [], risks: [],
        },
      },
    });
  });

  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByTestId("summary-status")).toHaveText("Analizando el transcript definitivo…");
  const result = page.getByTestId("summary-result");
  await expect(result).toBeVisible({ timeout: 10_000 });
  await expect(result.getByRole("heading").first()).toHaveText("Decisiones");
  await expect(result.getByText("Decidida")).toBeVisible();
  await expect(result.getByText("SPEAKER_00")).toBeVisible();

  await result.getByRole("button", { name: "00:12" }).first().click();
  await expect(page.locator("li.active")).toContainText("De acuerdo, publicamos el lunes.");
});

test("an extraction whose items were all dropped says so instead of claiming nothing was found", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route(`**/api/meetings/${MEETING_ID}`, (route) =>
    route.fulfill({
      json: {
        id: MEETING_ID, title: "Summary sense cites", description: null, status: "ready", started_at: null,
        ended_at: null, duration: 20, primary_language: ["ca"], created_by: null,
        created_at: "2026-09-30T10:00:00Z", updated_at: "2026-09-30T10:00:00Z", attendee_count: 1, tracks: [],
      },
    }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcription`, (route) =>
    route.fulfill({ status: 404, json: { detail: "TRANSCRIPTION_NOT_FOUND" } }),
  );
  await page.route(`**/api/meetings/${MEETING_ID}/transcript`, (route) => route.fulfill({ status: 404, json: {} }));
  await page.route(`**/api/meetings/${MEETING_ID}/summary`, (route) =>
    route.fulfill({
      json: {
        meeting_id: MEETING_ID, state: "empty", llm_configured: true,
        job: { status: "completed", model: "m", language: "ca", error: null, attempts: 1 },
        result: {
          summary: { text: "", evidence: [] }, decisions: [], actions: [], topics: [], open_questions: [], risks: [],
          dropped_items: 3,
        },
      },
    }),
  );
  await page.goto(`/meetings/${MEETING_ID}`);
  await expect(page.getByTestId("summary-empty")).toContainText("3 elemento(s)");
  await expect(page.getByTestId("summary-empty")).not.toContainText("no encontró");
});
