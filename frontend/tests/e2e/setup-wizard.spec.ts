import { expect, test } from "./fixtures";
import type { Page } from "./fixtures";

// The first-start wizard with a mocked backend; synthetic data only.
const FIRST_START = {
  llm_provider: "ollama",
  llm_base_url: "http://localhost:11434",
  llm_model: "",
  llm_output_language: "en",
  llm_configured: false,
  setup_completed: false,
  setup_required: true,
};

async function open(page: Page, current: Record<string, unknown>) {
  const puts: Record<string, unknown>[] = [];
  const asked: Record<string, unknown>[] = [];
  let state = current;
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/meetings/tags", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/meetings", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      puts.push(body);
      state = { ...state, ...body, llm_configured: Boolean(body.llm_model ?? state.llm_model), setup_required: false };
      return route.fulfill({ json: state });
    }
    return route.fulfill({ json: state });
  });
  await page.route("**/api/settings/models", (route) => {
    const body = route.request().postDataJSON();
    asked.push(body);
    if (String(body.base_url).includes("down")) return route.fulfill({ status: 502, json: { detail: "OPENAI_UNREACHABLE" } });
    return route.fulfill({ json: { base_url: body.base_url, models: ["ornith-chat", "ornith-rag"] } });
  });
  await page.goto("/");
  return { puts, asked };
}

test("a new installation is led through language, server and model and saves them", async ({ page }) => {
  const { puts, asked } = await open(page, FIRST_START);

  await expect(page.getByRole("heading", { name: "Welcome to AdVera" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Meetings" })).toHaveCount(0); // no menu yet
  await expect(page.getByTestId("setup-step")).toContainText("Step 1 of 4");
  await expect(page.getByTestId("setup-change-later")).toContainText("You can change all of this later in Settings.");

  // Choosing a language changes the wizard itself at once.
  await page.getByLabel("Español").check();
  await expect(page.getByRole("heading", { name: "Te damos la bienvenida a AdVera" })).toBeVisible();
  await expect(page.getByTestId("setup-change-later")).toContainText("Podrás cambiar todo esto más adelante en Ajustes.");
  await page.getByRole("button", { name: "Siguiente" }).click();

  // The server must be checked before going on.
  await expect(page.getByTestId("setup-step")).toContainText("Paso 2 de 4");
  await expect(page.getByTestId("setup-change-later")).toBeVisible();
  await expect(page.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  await page.getByLabel("Proveedor").selectOption("openai");
  await page.getByLabel("URL del servidor").fill("http://10.0.0.17:8080");
  await page.getByRole("button", { name: "Comprobar" }).click();
  await expect(page.getByText("Conectado: 2 modelos disponibles.")).toBeVisible();
  expect(asked.at(-1)).toEqual({ provider: "openai", base_url: "http://10.0.0.17:8080" });
  await page.getByRole("button", { name: "Siguiente" }).click();

  await expect(page.getByRole("button", { name: "Siguiente" })).toBeDisabled(); // a model is needed
  await expect(page.getByTestId("setup-change-later")).toBeVisible();
  await page.getByLabel("Modelo").selectOption("ornith-rag");
  await page.getByRole("button", { name: "Siguiente" }).click();

  const summary = page.getByTestId("setup-summary");
  await expect(summary).toContainText("Español");
  await expect(summary).toContainText("Compatible con OpenAI");
  await expect(summary).toContainText("http://10.0.0.17:8080");
  await expect(summary).toContainText("ornith-rag");
  await expect(page.getByTestId("setup-change-later")).toContainText("más adelante en Ajustes");
  await page.getByRole("button", { name: "Empezar a usar AdVera" }).click();

  // The application opens, in the chosen language.
  await expect(page.getByRole("link", { name: "Reuniones" })).toBeVisible();
  expect(puts).toEqual([
    {
      llm_provider: "openai",
      llm_base_url: "http://10.0.0.17:8080",
      llm_model: "ornith-rag",
      llm_output_language: "es",
      setup_completed: true,
    },
  ]);
});

test("going back keeps what was chosen and an unreachable server blocks the next step", async ({ page }) => {
  await open(page, FIRST_START);
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Provider").selectOption("openai");
  await page.getByLabel("Server URL").fill("http://down.test");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByRole("alert")).toContainText("Could not connect to the server.");
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();

  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByTestId("setup-step")).toContainText("Step 1 of 4");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByLabel("Server URL")).toHaveValue("http://down.test");
});

test("skipping saves only the language and the wizard does not come back", async ({ page }) => {
  const { puts } = await open(page, FIRST_START);
  await page.getByLabel("Català").check();
  await page.getByRole("button", { name: "Salta per ara" }).click();

  await expect(page.getByRole("link", { name: "Reunions" })).toBeVisible();
  expect(puts).toEqual([{ llm_output_language: "ca", setup_completed: true }]);
  await page.reload();
  await expect(page.getByRole("link", { name: "Reunions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /benvinguda/ })).toHaveCount(0);
});

test("an installation that already has a model never sees the wizard", async ({ page }) => {
  await open(page, { ...FIRST_START, llm_model: "ornith-1.5:35b", llm_configured: true, setup_required: false });
  await expect(page.getByRole("link", { name: "Meetings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Welcome to AdVera" })).toHaveCount(0);
});
