import { expect, test as base } from "@playwright/test";

// The interface language comes from Settings (English by default). These tests check the
// Spanish texts, so every page sees Spanish unless a test answers /api/settings itself
// (a route registered later in the test takes precedence over this one).
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route("**/api/settings", (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      return route.fulfill({
        json: { llm_provider: "ollama", llm_base_url: "", llm_model: "", llm_output_language: "es", llm_configured: false },
      });
    });
    await use(page);
  },
});

export { expect };
export type { Page, Route } from "@playwright/test";
