import { defineConfig, devices } from "@playwright/test";

// Screenshots for the README and the landing page, from fictitious demo data (no backend):
//   npx playwright test -c playwright.screenshots.config.ts
// They are written to docs/screenshots/.
const PORT = 5191;

export default defineConfig({
  testDir: "tests/screenshots",
  workers: 1,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://localhost:${PORT}`,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    locale: "en-US",
    timezoneId: "Europe/Madrid",
  },
  webServer: {
    command: `npx vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
  },
});
