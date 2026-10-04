import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { z } from "zod";

import { ApiError, describeError } from "../../api";
import { formatDate } from "../../format";
import i18n from "../../i18n";

// Health of the system at a glance: services, workers, queues, and the latest summaries and
// searches (rebuild-system-monitor.md). Read only; it asks again every few seconds.
const REFRESH_MS = 5_000;
const WORKERS = ["transcription", "summary", "brain-index", "brain-query"] as const;
type Kind = (typeof WORKERS)[number];

const instanceSchema = z.object({
  host: z.string(),
  pid: z.number().nullable().optional(),
  started_at: z.string().nullable().optional(),
  job_id: z.string().nullable().optional(),
});
const recentSchema = z.object({
  id: z.string(),
  status: z.string(),
  attempts: z.number(),
  max_attempts: z.number(),
  error: z.string().nullable(),
  meeting_id: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  duration_seconds: z.number().nullable().optional(),
});
const monitorSchema = z.object({
  generated_at: z.string(),
  services: z.array(z.object({ name: z.string(), ok: z.boolean(), latency_ms: z.number().nullable().optional() })),
  llm: z.object({ configured: z.boolean(), base_url: z.string(), model: z.string() }),
  workers: z.array(
    z.object({
      name: z.string(),
      state: z.enum(["up", "down", "unknown"]),
      instances: z.array(instanceSchema),
      since: z.string().nullable().optional(),
    }),
  ),
  queues: z.array(
    z.object({
      name: z.string(),
      state: z.enum(["ok", "busy", "stalled", "unknown"]),
      stream_length: z.number().nullable().optional(),
      pending: z.number().nullable().optional(),
      lag: z.number().nullable().optional(),
      consumers_gone: z.number(),
    }),
  ),
  jobs: z.array(
    z.object({
      name: z.string(),
      queued: z.number(),
      running: z.number(),
      completed: z.number(),
      failed: z.number(),
      oldest_queued_seconds: z.number().nullable().optional(),
      stale: z.number(),
      completed_last_hour: z.number(),
      average_seconds: z.number().nullable().optional(),
      last_failures: z.array(z.object({ id: z.string(), error: z.string().nullable(), at: z.string().nullable() })),
    }),
  ),
  recent: z.record(z.string(), z.array(recentSchema)),
});
type Monitor = z.infer<typeof monitorSchema>;
type Recent = z.infer<typeof recentSchema>;

async function fetchMonitor(): Promise<Monitor> {
  const response = await fetch("/api/monitor");
  if (!response.ok) throw new ApiError(response.status, `HTTP_${response.status}`);
  return monitorSchema.parse(await response.json());
}

function duration(seconds: number | null | undefined): string {
  if (seconds == null) return i18n.t("common.none");
  const total = Math.round(seconds);
  if (total < 60) return `${total} s`;
  if (total < 3600) return `${Math.floor(total / 60)} min ${String(total % 60).padStart(2, "0")} s`;
  return `${Math.floor(total / 3600)} h ${String(Math.floor((total % 3600) / 60)).padStart(2, "0")} min`;
}

// The state is always written, never only coloured.
function State({ state }: { state: string }) {
  const { t } = useTranslation();
  return <span className={`state state-${state}`}>{t(`system.state.${state as "up"}`)}</span>;
}

function RecentTable({ rows, kind }: { rows: Recent[]; kind: Kind }) {
  const { t } = useTranslation();
  if (!rows.length) return <p className="hint">{t("system.empty")}</p>;
  return (
    <table className="system-table">
      <thead>
        <tr>
          <th>{kind === "brain-query" ? t("system.search") : t("system.meeting")}</th>
          <th>{t("system.status")}</th>
          <th>{t("system.attempts")}</th>
          <th>{t("system.duration")}</th>
          <th>{t("system.when")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} data-testid={`recent-${kind}`}>
            <td>
              {row.meeting_id ? (
                <Link to={`/meetings/${row.meeting_id}`}>{row.title || row.meeting_id}</Link>
              ) : (
                (row.title ?? i18n.t("common.none"))
              )}
            </td>
            <td>
              <span className={`state state-job-${row.status}`}>
                {t(`system.job.${row.status as "queued"}`, { defaultValue: row.status })}
              </span>
              {row.error && <span className="hint"> {describeError(row.error)}</span>}
            </td>
            <td>
              {row.attempts}/{row.max_attempts}
            </td>
            <td>{duration(row.duration_seconds)}</td>
            <td>{row.created_at ? formatDate(row.created_at, "medium") : i18n.t("common.none")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SystemPage() {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ["monitor"], queryFn: fetchMonitor, refetchInterval: REFRESH_MS, retry: false });
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const data = query.data;
  const ago = query.dataUpdatedAt ? Math.max(0, Math.round((now - query.dataUpdatedAt) / 1_000)) : null;
  const jobs = Object.fromEntries((data?.jobs ?? []).map((job) => [job.name, job]));
  const queues = Object.fromEntries((data?.queues ?? []).map((queue) => [queue.name, queue]));
  const serviceName = (name: string) => t(`system.services.${name as "api"}`, { defaultValue: name });

  return (
    <section className="system">
      <h1>{t("system.title")}</h1>
      <p className="hint" data-testid="system-updated">
        {query.isError ? (
          <span role="alert">{t("system.loadError")}</span>
        ) : ago === null ? (
          t("common.loading")
        ) : (
          t("system.updated", { seconds: ago })
        )}
      </p>
      {data && (
        <>
          <h2>{t("system.servicesTitle")}</h2>
          <div className="system-grid">
            {data.services.map((service) => (
              <div className="system-card" key={service.name} data-testid={`service-${service.name}`}>
                <strong>{serviceName(service.name)}</strong>
                <State state={service.ok ? "up" : "down"} />
                {service.latency_ms != null && <span className="hint">{service.latency_ms} ms</span>}
              </div>
            ))}
            <div className="system-card" data-testid="service-llm">
              <strong>{t("system.services.llm")}</strong>
              <State state={data.llm.configured ? "up" : "unknown"} />
              <span className="hint">
                {data.llm.configured ? `${data.llm.model} · ${data.llm.base_url}` : t("system.llmNone")}
              </span>
            </div>
          </div>

          <h2>{t("system.workersTitle")}</h2>
          <div className="system-grid">
            {data.workers.map((worker) => {
              const queue = queues[worker.name];
              const stats = jobs[worker.name];
              const busy = worker.instances.find((instance) => instance.job_id);
              return (
                <div className="system-card system-worker" key={worker.name} data-testid={`worker-${worker.name}`}>
                  <strong>{t(`system.workers.${worker.name as Kind}`, { defaultValue: worker.name })}</strong>
                  <State state={worker.state} />
                  {worker.state === "up" && worker.since && (
                    <span className="hint">{t("system.since", { time: formatDate(worker.since, "medium") })}</span>
                  )}
                  {worker.state === "up" && (
                    <span className="hint">{busy ? t("system.working", { job: busy.job_id }) : t("system.idle")}</span>
                  )}
                  {queue && (
                    <dl className="system-facts">
                      <dt>{t("system.queue")}</dt>
                      <dd data-testid={`queue-${worker.name}`}>
                        <State state={queue.state} />
                      </dd>
                      <dt>{t("system.waiting")}</dt>
                      <dd>{stats?.queued ?? t("common.none")}</dd>
                      <dt>{t("system.running")}</dt>
                      <dd>{stats?.running ?? t("common.none")}</dd>
                      <dt>{t("system.inStream")}</dt>
                      <dd>{queue.stream_length ?? t("common.none")}</dd>
                      <dt>{t("system.pending")}</dt>
                      <dd>{queue.pending ?? t("common.none")}</dd>
                      {stats?.oldest_queued_seconds != null && (
                        <>
                          <dt>{t("system.oldest")}</dt>
                          <dd>{duration(stats.oldest_queued_seconds)}</dd>
                        </>
                      )}
                      {stats && stats.stale > 0 && (
                        <>
                          <dt>{t("system.stale")}</dt>
                          <dd className="state-down">{stats.stale}</dd>
                        </>
                      )}
                      <dt>{t("system.lastHour")}</dt>
                      <dd>{stats?.completed_last_hour ?? t("common.none")}</dd>
                      <dt>{t("system.average")}</dt>
                      <dd>{duration(stats?.average_seconds)}</dd>
                      <dt>{t("system.failed")}</dt>
                      <dd>{stats?.failed ?? t("common.none")}</dd>
                    </dl>
                  )}
                  {stats?.last_failures.map((failure) => (
                    <p className="hint system-failure" key={failure.id}>
                      {describeError(failure.error)}
                    </p>
                  ))}
                </div>
              );
            })}
          </div>

          <h2>{t("system.summariesTitle")}</h2>
          <RecentTable rows={data.recent.summary ?? []} kind="summary" />
          <h2>{t("system.searchesTitle")}</h2>
          <RecentTable rows={data.recent["brain-query"] ?? []} kind="brain-query" />
          <details className="system-more">
            <summary>{t("system.moreTitle")}</summary>
            <h3>{t("system.workers.transcription")}</h3>
            <RecentTable rows={data.recent.transcription ?? []} kind="transcription" />
            <h3>{t("system.workers.brain-index")}</h3>
            <RecentTable rows={data.recent["brain-index"] ?? []} kind="brain-index" />
          </details>
        </>
      )}
    </section>
  );
}
