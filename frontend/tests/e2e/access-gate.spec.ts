import { expect, test } from "@playwright/test";

// ADR 0019: a token-protected API asks for the shared token once; the app loads after it.
test("asks for the access token, rejects a wrong one and opens the app with the right one", async ({ page }) => {
  let authenticated = false;
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/session", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      const ok = request.postDataJSON().token === "right-token";
      authenticated = authenticated || ok;
      return route.fulfill(ok ? { status: 204 } : { status: 401, json: { detail: "INVALID_TOKEN" } });
    }
    return route.fulfill({ json: { access: authenticated ? "authenticated" : "required" } });
  });
  await page.route("**/api/meetings", (route) => route.fulfill({ json: [] }));

  await page.goto("/");
  await expect(page.getByLabel("Token de acceso")).toBeVisible();
  await expect(page.getByRole("link", { name: "Reuniones" })).toHaveCount(0);

  await page.getByLabel("Token de acceso").fill("wrong");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("alert")).toContainText("Token incorrecto");

  await page.getByLabel("Token de acceso").fill("right-token");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("link", { name: "Reuniones" })).toBeVisible();
  await expect(page.getByLabel("Token de acceso")).toHaveCount(0);
});
