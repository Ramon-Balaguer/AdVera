import { expect, test } from "./fixtures";
import type { Page } from "./fixtures";

// The system page with a mocked backend; synthetic data only.
const NAMES = ["transcription", "summary", "brain-index", "brain-query"] as const;

function stats(name: string, extra: Record<string, unknown> = {}) {
  return {
    name,
    queued: 0,
    running: 0,
    completed: 10,
    failed: 0,
    oldest_queued_seconds: null,
    stale: 0,
    completed_last_hour: 2,
    average_seconds: 75,
    last_failures: [],
    ...extra,
  };
}

function payload(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: "2026-10-04T10:00:00+00:00",
    services: [
      { name: "api", ok: true, latency_ms: null },
      { name: "redis", ok: true, latency_ms: 2 },
      { name: "postgres", ok: true, latency_ms: 3 },
    ],
    llm: { configured: true, base_url: "http://llm.test", model: "modelo-prueba" },
    workers: NAMES.map((name) => ({
      name,
      state: "up",
      instances: [{ host: "h1", pid: 7, started_at: "2026-10-04T08:00:00+00:00", job_id: null }],
      since: "2026-10-04T08:00:00+00:00",
    })),
    queues: NAMES.map((name) => ({
      name,
      state: "ok",
      stream_length: 0,
      pending: 0,
      lag: 0,
      consumers_gone: 0,
    })),
    jobs: NAMES.map((name) => stats(name)),
    recent: {
      transcription: [],
      "brain-index": [],
      summary: [
        {
          id: "s1",
          status: "completed",
          attempts: 1,
          max_attempts: 3,
          error: null,
          meeting_id: "m1",
          title: "Sincro semanal",
          created_at: "2026-10-04T09:00:00+00:00",
          duration_seconds: 125,
        },
      ],
      "brain-query": [
        {
          id: "q1",
          status: "failed",
          attempts: 1,
          max_attempts: 1,
          error: "LLM_UNAVAILABLE",
          meeting_id: null,
          title: "¿Qué decidimos sobre el almacenamiento?",
          created_at: "2026-10-04T09:30:00+00:00",
          duration_seconds: null,
        },
      ],
    },
    ...overrides,
  };
}

async function open(page: Page, bodies: unknown[]) {
  let calls = 0;
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/monitor", (route) => {
    const body = bodies[Math.min(calls, bodies.length - 1)];
    calls += 1;
    return route.fulfill({ json: body });
  });
  await page.goto("/system");
}

test("a healthy system shows every service and worker as active and lists the latest work", async ({ page }) => {
  await open(page, [payload()]);

  await expect(page.getByRole("heading", { name: "Sistema" })).toBeVisible();
  await expect(page.getByTestId("service-redis")).toContainText("Activo");
  await expect(page.getByTestId("service-postgres")).toContainText("3 ms");
  await expect(page.getByTestId("service-llm")).toContainText("modelo-prueba");
  for (const name of NAMES) {
    await expect(page.getByTestId(`worker-${name}`)).toContainText("Activo");
    await expect(page.getByTestId(`queue-${name}`)).toContainText("Bien");
  }
  await expect(page.getByTestId("worker-summary")).toContainText("Esperando trabajo");
  await expect(page.getByTestId("system-updated")).toContainText("Actualizado hace");

  const summary = page.getByTestId("recent-summary");
  await expect(summary.getByRole("link", { name: "Sincro semanal" })).toHaveAttribute("href", "/meetings/m1");
  await expect(summary).toContainText("2 min 05 s");
  const search = page.getByTestId("recent-brain-query");
  await expect(search).toContainText("¿Qué decidimos sobre el almacenamiento?");
  await expect(search).toContainText("Fallido");
});

test("a worker that is down with work waiting makes its queue stalled, in words", async ({ page }) => {
  const body = payload({
    workers: NAMES.map((name) => ({
      name,
      state: name === "summary" ? "down" : "up",
      instances: name === "summary" ? [] : [{ host: "h1", pid: 7, started_at: "2026-10-04T08:00:00+00:00", job_id: name === "brain-query" ? "job-42" : null }],
      since: name === "summary" ? null : "2026-10-04T08:00:00+00:00",
    })),
    queues: NAMES.map((name) => ({
      name,
      state: name === "summary" ? "stalled" : name === "brain-query" ? "busy" : "ok",
      stream_length: name === "summary" ? 3 : 0,
      pending: 0,
      lag: name === "summary" ? 3 : 0,
      consumers_gone: 0,
    })),
    jobs: NAMES.map((name) =>
      name === "summary"
        ? stats(name, { queued: 3, oldest_queued_seconds: 400, stale: 1, last_failures: [{ id: "x", error: "LEASE_EXPIRED", at: null }] })
        : stats(name),
    ),
  });
  await open(page, [body]);

  const worker = page.getByTestId("worker-summary");
  await expect(worker).toContainText("Caído");
  await expect(page.getByTestId("queue-summary")).toContainText("Parada");
  await expect(worker).toContainText("6 min 40 s");
  await expect(worker).toContainText("Sin latido");
  await expect(worker).toContainText("El proceso de transcripción se interrumpió");
  await expect(page.getByTestId("worker-brain-query")).toContainText("Trabajando en job-42");
  await expect(page.getByTestId("queue-brain-query")).toContainText("Ocupada");
});

test("a service that does not answer is shown as down and unknown workers are not called down", async ({ page }) => {
  const body = payload({
    services: [
      { name: "api", ok: true },
      { name: "redis", ok: false },
      { name: "postgres", ok: true, latency_ms: 4 },
    ],
    workers: NAMES.map((name) => ({ name, state: "unknown", instances: [], since: null })),
    queues: NAMES.map((name) => ({ name, state: "unknown", consumers_gone: 0 })),
  });
  await open(page, [body]);

  await expect(page.getByTestId("service-redis")).toContainText("Caído");
  await expect(page.getByTestId("worker-transcription")).toContainText("Desconocido");
  await expect(page.getByTestId("worker-transcription")).not.toContainText("Caído");
});

test("the page asks again by itself and shows the new state", async ({ page }) => {
  const later = payload({
    workers: NAMES.map((name) => ({
      name,
      state: name === "brain-index" ? "down" : "up",
      instances: name === "brain-index" ? [] : [{ host: "h1", pid: 7, started_at: "2026-10-04T08:00:00+00:00", job_id: null }],
      since: null,
    })),
  });
  await open(page, [payload(), later]);

  await expect(page.getByTestId("worker-brain-index")).toContainText("Activo");
  await expect(page.getByTestId("worker-brain-index")).toContainText("Caído", { timeout: 15_000 });
});

test("when the status cannot be loaded the page says so", async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ json: { service: "advera-api", status: "ok" } }));
  await page.route("**/api/capture-agent/capabilities", (route) => route.fulfill({ json: { available: false, tracks: {} } }));
  await page.route("**/api/monitor", (route) => route.fulfill({ status: 500, json: {} }));
  await page.goto("/system");

  await expect(page.getByRole("alert")).toContainText("No se pudo cargar el estado del sistema");
});
