import { defineConfig, devices } from "@playwright/test";

// Live end-to-end runs against a deployed AdVera with the `bot` profile and real calls
// (tests/e2e-live). Nothing is mocked and nothing is started here: ADVERA_LIVE_URL points at
// the running stack. It records real people, so it only runs with LIVE_CONSENT=yes.
export default defineConfig({
  testDir: "tests/e2e-live",
  workers: 1,
  timeout: 30 * 60_000,
  expect: { timeout: 15_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.ADVERA_LIVE_URL ?? "http://localhost:15173",
    trace: "retain-on-failure",
  },
});
