import { expect, test } from "./fixtures";

test("blocks the app until /api/health succeeds, then renders it", async ({ page }) => {
  let healthy = false;
  await page.route("**/api/meetings", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({ json: { available: false, tracks: {} } }),
  );
  await page.route("**/api/health", (route) =>
    healthy
      ? route.fulfill({ status: 200, json: { status: "ok" } })
      : route.fulfill({ status: 503, body: "" }),
  );
  await page.clock.install();

  await page.goto("/");
  // The language is unknown until the API answers, so the gate speaks English.
  await expect(page.getByText("AdVera is starting")).toBeVisible();

  healthy = true;
  await page.clock.runFor(5000);

  await expect(page.getByRole("status")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Reuniones" })).toBeVisible();
});

test("keeps the app blocked on network errors", async ({ page }) => {
  await page.route("**/api/capture-agent/capabilities", (route) =>
    route.fulfill({ json: { available: false, tracks: {} } }),
  );
  await page.route("**/api/health", (route) => route.abort());

  await page.goto("/");

  // The language is unknown until the API answers, so the gate speaks English.
  await expect(page.getByText("AdVera is starting")).toBeVisible();
});
