import { defineConfig, devices } from "@playwright/test";

// A dedicated strict port so E2E never runs against another app already on 5173.
const E2E_PORT = 5190;

export default defineConfig({
  testDir: "tests/e2e",
  use: { baseURL: `http://localhost:${E2E_PORT}` },
  webServer: {
    command: `npx vite --port ${E2E_PORT} --strictPort`,
    url: `http://localhost:${E2E_PORT}`,
    reuseExistingServer: false,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Synthetic microphone: Chromium's fake capture device, never a real mic.
        permissions: ["microphone"],
        launchOptions: {
          args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
        },
      },
    },
  ],
});
