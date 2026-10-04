import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { z } from "zod";

import { ApiError, describeError } from "../../api";
import i18n from "../../i18n";
import { formatTimestamp } from "../../format";

// Summary panel (summary-extraction-from-definitive-transcript.md): Decisions first, every item
// cites definitive transcript segments that open the audio at the right second.
const evidenceSchema = z.object({
  segment_id: z.string(),
  start: z.number().nullable(), // a note block has no time (ADR 0020)
  end: z.number().nullable(),
  speaker: z.string().nullable().optional(),
  track: z.string().nullable().optional(),
});
const itemSchema = z.object({
  text: z.string(),
  evidence: z.array(evidenceSchema),
  state: z.string().optional(),
  owner: z.string().nullable().optional(),
  due_date: z.string().nullable().optional(),
});
type SummaryItem = z.infer<typeof itemSchema>;
const summarySchema = z.object({
  meeting_id: z.string(),
  state: z.enum(["blocked", "not_started", "queued", "running", "completed", "empty", "failed"]),
  llm_configured: z.boolean(),
  job: z
    .object({ status: z.string(), model: z.string(), language: z.string(), error: z.string().nullable(), attempts: z.number() })
    .nullable()
    .optional(),
  result: z
    .object({
      summary: z.object({ text: z.string(), evidence: z.array(evidenceSchema) }),
      decisions: z.array(itemSchema),
      actions: z.array(itemSchema),
      topics: z.array(itemSchema),
      open_questions: z.array(itemSchema),
      risks: z.array(itemSchema),
      // Items the model produced without a valid citation are never stored; only their count is.
      dropped_items: z.number().optional(),
    })
    .nullable()
    .optional(),
});
type Summary = z.infer<typeof summarySchema>;

const DECISION_STATES = ["decided", "proposed", "rejected", "superseded", "unknown"] as const;
const SUMMARY_ERRORS = [
  "LLM_NOT_CONFIGURED",
  "LLM_UNAVAILABLE",
  "LLM_MODEL_NOT_FOUND",
  "LLM_INVALID_JSON",
  "SUMMARY_SCHEMA_INVALID",
  "TRANSCRIPT_TOO_LONG",
  "INPUT_CHANGED",
] as const;

/** A Summary error in words: Summary's own codes first, then the shared API messages. */
function summaryError(code: string | null | undefined): string {
  return (SUMMARY_ERRORS as readonly string[]).includes(code ?? "")
    ? i18n.t(`summary.errors.${code as (typeof SUMMARY_ERRORS)[number]}`)
    : describeError(code);
}

async function fetchSummary(meetingId: string): Promise<Summary> {
  const response = await fetch(`/api/meetings/${meetingId}/summary`);
  if (!response.ok) throw new ApiError(response.status, `HTTP_${response.status}`);
  return summarySchema.parse(await response.json());
}

async function regenerate(meetingId: string): Promise<void> {
  const response = await fetch(`/api/meetings/${meetingId}/summary`, { method: "POST" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : "HTTP_ERROR");
  }
}

/** "note-003" -> "Apuntes ¶3": how a cited note block is shown. */
export function noteLabel(blockId: string) {
  return i18n.t("notes.paragraph", { n: Number(blockId.replace(/^note-/, "")) || blockId });
}

function Citations({ item, onSeek }: { item: Pick<SummaryItem, "evidence">; onSeek: (segmentId: string) => void }) {
  const { t } = useTranslation();
  return (
    <span className="citations">
      {item.evidence.map((evidence) => (
        <button
          key={evidence.segment_id}
          type="button"
          className="citation"
          onClick={() => onSeek(evidence.segment_id)}
          title={evidence.track === "notes" ? t("summary.goToNote") : t("summary.goToSegment", { id: evidence.segment_id })}
        >
          {evidence.track === "notes" || evidence.start === null
            ? noteLabel(evidence.segment_id)
            : formatTimestamp(evidence.start)}
        </button>
      ))}
    </span>
  );
}

function Section({ title, items, onSeek }: { title: string; items: SummaryItem[]; onSeek: (id: string) => void }) {
  if (items.length === 0) return null;
  return (
    <div className="summary-section">
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => (
          <li key={index}>
            {item.state && (
              <span className={`badge badge-${item.state}`}>
                {(DECISION_STATES as readonly string[]).includes(item.state)
                  ? i18n.t(`summary.state.${item.state as (typeof DECISION_STATES)[number]}`)
                  : item.state}
              </span>
            )}
            <span>{item.text}</span>
            {item.owner && <span className="meta"> · {item.owner}</span>}
            {item.due_date && <span className="meta"> · {item.due_date}</span>}
            <Citations item={item} onSeek={onSeek} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SummaryPanel({ meetingId, onSeek }: { meetingId: string; onSeek: (segmentId: string) => void }) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const summary = useQuery({
    queryKey: ["summary", meetingId],
    queryFn: () => fetchSummary(meetingId),
    refetchInterval: (query) =>
      query.state.data?.state === "queued" || query.state.data?.state === "running" ? 3000 : false,
  });
  const generate = useMutation({
    mutationFn: () => regenerate(meetingId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["summary", meetingId] }),
  });

  const data = summary.data;
  if (!data) return null;
  const result = data.result;
  const busy = data.state === "queued" || data.state === "running";
  const canGenerate = data.llm_configured && !busy && data.state !== "blocked";

  return (
    <section className="summary" aria-label={t("summary.region")}>
      <div className="row summary-header">
        <h2>{t("summary.title")}</h2>
        {data.state !== "blocked" && (
          <button type="button" disabled={!canGenerate || generate.isPending} onClick={() => generate.mutate()}>
            {data.state === "not_started" ? t("summary.generate") : data.state === "failed" ? t("summary.retry") : t("summary.regenerate")}
          </button>
        )}
        {data.job && <span className="meta">{data.job.model}</span>}
      </div>

      {data.state === "blocked" && <p className="hint">{t("summary.blocked")}</p>}
      {!data.llm_configured && data.state !== "blocked" && (
        <p className="hint">
          {t("summary.configureBefore")}
          <Link to="/settings">{t("nav.settings")}</Link>
          {t("summary.configureAfter")}
        </p>
      )}
      {busy && (
        <p role="status" aria-live="polite" data-testid="summary-status">
          {data.state === "queued" ? t("summary.queued") : t("summary.running")}
        </p>
      )}
      {data.state === "failed" && (
        <p role="alert">
          {t("summary.failed", { reason: summaryError(data.job?.error) })}
        </p>
      )}
      {generate.isError && (
        <p role="alert">{summaryError((generate.error as ApiError).code)}</p>
      )}
      {data.state === "empty" && (
        <p data-testid="summary-empty">
          {result?.dropped_items
            ? t("summary.emptyDropped", { count: result.dropped_items })
            : t("summary.empty")}
        </p>
      )}

      {result && data.state === "completed" && (
        <div data-testid="summary-result">
          <Section title={t("summary.decisions")} items={result.decisions} onSeek={onSeek} />
          {result.summary.text && (
            <div className="summary-section">
              <h3>{t("summary.summary")}</h3>
              <p>
                {result.summary.text} <Citations item={result.summary} onSeek={onSeek} />
              </p>
            </div>
          )}
          <Section title={t("summary.actions")} items={result.actions} onSeek={onSeek} />
          <Section title={t("summary.topics")} items={result.topics} onSeek={onSeek} />
          <Section title={t("summary.openQuestions")} items={result.open_questions} onSeek={onSeek} />
          <Section title={t("summary.risks")} items={result.risks} onSeek={onSeek} />
          {result.dropped_items ? (
            <p className="hint" data-testid="summary-dropped">
              {t("summary.dropped", { count: result.dropped_items })}
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
