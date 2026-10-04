import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { z } from "zod";

import { api, describeError } from "../../api";
import { formatTimestamp } from "../../format";
import i18n from "../../i18n";
import { parseFrame } from "../../ws";
import { ConceptGraphSection } from "./ConceptGraphSection";
import { sourceLink, sourceWhen } from "./links";
import { TagPicker } from "../tags/TagPicker";

// Global Memory Q&A (spec §15; brain-memoria-global.md; brain-query-results-websocket.md).
// A factual answer is shown only with sources that open the meeting at the cited second.

const sourceSchema = z.object({
  meeting_id: z.string(),
  meeting_title: z.string(),
  meeting_date: z.string(),
  segment_id: z.string(),
  start: z.number(),
  end: z.number(),
  speaker: z.string().nullable(),
  person: z.string().nullable().optional(), // ADR 0021
  track: z.string().nullable().optional(), // "notes" for a note block (ADR 0020)
  language: z.string().nullable(),
  text: z.string(),
});
type Source = z.infer<typeof sourceSchema>;

// A fragment the search found. Runs saved before the text and segment were kept have neither,
// so they show as a plain line instead of a link.
const retrievedSchema = z.object({
  meeting_id: z.string(),
  meeting_title: z.string(),
  start: z.number(),
  segment_id: z.string().nullable().optional(),
  content: z.string().optional(),
  speaker: z.string().nullable().optional(),
  person: z.string().nullable().optional(),
  track: z.string().nullable().optional(),
  language: z.string().nullable().optional(),
});
type Retrieved = z.infer<typeof retrievedSchema>;

const querySchema = z.object({
  query_id: z.string(),
  query: z.string(),
  status: z.enum(["queued", "retrieving", "synthesizing", "completed", "empty", "failed"]),
  error: z.string().nullable(),
  result: z
    .object({
      answer: z.string().nullable(),
      sources: z.array(sourceSchema),
      retrieval: z.string().optional(),
      // Why no answer was shown (runs saved before this was kept have none).
      reason: z.string().optional(),
      retrieved: z.array(retrievedSchema).optional(),
    })
    .nullable(),
});
type QueryRun = z.infer<typeof querySchema>;

const overviewSchema = z.object({
  state: z.enum(["empty", "indexing", "partial", "ready"]),
  meetings_indexed: z.number(),
  chunks: z.number(),
  embedded_chunks: z.number(),
  jobs_pending: z.number(),
  jobs_failed: z.number(),
  llm_configured: z.boolean(),
});

const STATUSES = ["queued", "retrieving", "synthesizing", "empty", "failed"] as const;
const REASONS = ["NO_MATCH", "NO_SEGMENTS", "MODEL_INSUFFICIENT", "UNCITED", "INVALID_ANSWER"] as const;
const OVERVIEW_STATES = ["empty", "indexing", "partial"] as const;
const MEMORY_ERRORS = ["LLM_NOT_CONFIGURED", "LLM_UNAVAILABLE", "QUEUE_UNAVAILABLE"] as const;
const has = (list: readonly string[], value: string | null | undefined): boolean => list.includes(value ?? "");

const statusText = (status: string) =>
  has(STATUSES, status) ? i18n.t(`memory.status.${status as (typeof STATUSES)[number]}`) : "";
const reasonText = (reason: string | null | undefined) =>
  has(REASONS, reason) ? i18n.t(`memory.reason.${reason as (typeof REASONS)[number]}`) : "";
const overviewText = (state: string) =>
  has(OVERVIEW_STATES, state) ? i18n.t(`memory.state.${state as (typeof OVERVIEW_STATES)[number]}`) : "";
const errorText = (code: string | null | undefined) =>
  has(MEMORY_ERRORS, code)
    ? i18n.t(`memory.errors.${code as (typeof MEMORY_ERRORS)[number]}`)
    : describeError(code);

function wsUrl(path: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${path}`;
}

export { sourceLink };

// The last search (form + summary + sources) lives in the browser so that coming back from a
// meeting with the browser's back button shows it again, pre-filled, to open other references.
const STORAGE_KEY = "advera.memory.search";
const TERMINAL = ["completed", "empty", "failed"];
const RECOVERY_ATTEMPTS = 40;
const RECOVERY_INTERVAL_MS = 3_000;
const savedSchema = z.object({
  question: z.string(),
  language: z.string(),
  dateFrom: z.string(),
  dateTo: z.string(),
  tag: z.string().default(""), // one tag, as saved before several could be chosen
  tags: z.array(z.string()).default([]),
  run: querySchema.nullable(),
});
type Saved = z.infer<typeof savedSchema>;

function loadSaved(): Saved | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? savedSchema.safeParse(JSON.parse(raw)) : null;
    return parsed?.success ? parsed.data : null;
  } catch {
    return null;
  }
}

export function MemoryPage() {
  const { t } = useTranslation();
  const overview = useQuery({
    queryKey: ["memory-overview"],
    queryFn: async () => overviewSchema.parse(await (await fetch("/api/memory/overview")).json()),
    refetchInterval: 15_000,
  });
  const [saved] = useState(loadSaved);
  const [question, setQuestion] = useState(saved?.question ?? "");
  const [language, setLanguage] = useState(saved?.language ?? "");
  const [tags, setTags] = useState<string[]>(saved?.tags.length ? saved.tags : saved?.tag ? [saved.tag] : []);
  const tagOptions = useQuery({ queryKey: ["tags"], queryFn: api.listTags });
  const [dateFrom, setDateFrom] = useState(saved?.dateFrom ?? "");
  const [dateTo, setDateTo] = useState(saved?.dateTo ?? "");
  const [run, setRun] = useState<QueryRun | null>(saved?.run ?? null);
  const [error, setError] = useState<string | null>(null);
  const socket = useRef<WebSocket | null>(null);

  useEffect(
    () => () => {
      const ws = socket.current;
      socket.current = null; // so that its close does not start the HTTP recovery
      ws?.close();
    },
    [],
  );

  useEffect(() => {
    try {
      const value: Saved = { question, language, dateFrom, dateTo, tag: "", tags, run };
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch {
      // Storage may be unavailable or full; the search still works, it is just not remembered.
    }
  }, [question, language, dateFrom, dateTo, tags, run]);

  const follow = (queryId: string) => {
    socket.current?.close();
    const ws = new WebSocket(wsUrl(`/ws/query/${queryId}`));
    socket.current = ws;
    ws.onmessage = (message) => {
      const event = parseFrame(message.data);
      const state = event?.type === "query.state" ? querySchema.safeParse(event) : null;
      if (state?.success) setRun(state.data);
    };
    ws.onerror = () => ws.close();
    ws.onclose = () => {
      if (socket.current === ws) void recover(queryId, ws);
    };
  };

  // HTTP is the durable recovery path if the socket drops before a terminal state: ask again
  // until the query ends, the page moves on to another query, or the server stays unreachable.
  const recover = async (queryId: string, ws: WebSocket) => {
    for (let attempt = 0; attempt < RECOVERY_ATTEMPTS; attempt++) {
      try {
        const response = await fetch(`/api/memory/query/${queryId}`);
        if (socket.current !== ws) return;
        const state = response.ok ? querySchema.safeParse(await response.json()) : null;
        if (state?.success) {
          setRun(state.data);
          if (TERMINAL.includes(state.data.status)) return;
        }
      } catch {
        // the server is unreachable for now: try again below
      }
      await new Promise((resolve) => setTimeout(resolve, RECOVERY_INTERVAL_MS));
      if (socket.current !== ws) return;
    }
    setError("NETWORK_ERROR");
  };

  useEffect(() => {
    if (saved?.run && !TERMINAL.includes(saved.run.status)) follow(saved.run.query_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (question.trim().length < 2) return;
    setError(null);
    const filters: Record<string, string | string[]> = {};
    if (language) filters.language = language;
    if (tags.length) filters.tags = tags; // meetings with any of them
    if (dateFrom) filters.date_from = `${dateFrom}T00:00:00Z`;
    if (dateTo) filters.date_to = `${dateTo}T23:59:59Z`;
    let response: Response;
    try {
      response = await fetch("/api/memory/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question.trim(), filters }),
      });
    } catch {
      setError("NETWORK_ERROR");
      return;
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : "HTTP_ERROR");
      return;
    }
    const parsed = querySchema.safeParse(body);
    if (!parsed.success) {
      setError("INVALID_RESPONSE");
      return;
    }
    const created = parsed.data;
    setRun(created);
    if (created.status !== "failed") follow(created.query_id);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) void submit();
  };

  const busy = run !== null && ["queued", "retrieving", "synthesizing"].includes(run.status);
  const data = overview.data;

  return (
    <section>
      <h1>{t("memory.title")}</h1>
      {data && (
        <p className="hint" data-testid="memory-overview">
          {t("memory.overview", { meetings: data.meetings_indexed, chunks: data.chunks, embedded: data.embedded_chunks })}
          {overviewText(data.state) && ` · ${overviewText(data.state)}`}
        </p>
      )}
      <form className="memory-form" onSubmit={submit}>
        <label htmlFor="memory-question">{t("memory.question")}</label>
        <textarea
          id="memory-question"
          rows={3}
          value={question}
          maxLength={500}
          placeholder={t("memory.questionPlaceholder")}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="row">
          <label>
            {t("memory.language")}{" "}
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="">{t("common.allMasc")}</option>
              <option value="ca">Català</option>
              <option value="es">Español</option>
              <option value="en">English</option>
            </select>
          </label>
          {(tagOptions.data?.length ?? 0) > 0 && (
            <div className="grow">
              <TagPicker
                value={tags}
                onChange={setTags}
                options={tagOptions.data ?? []}
                allowNew={false}
                label={t("memory.filterTags")}
                placeholder={t("memory.tagsPlaceholder")}
              />
            </div>
          )}
          <label>
            {t("memory.from")} <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label>
            {t("memory.to")} <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
          <button type="submit" disabled={busy || question.trim().length < 2}>
            {t("memory.ask")}
          </button>
          <span className="meta">Ctrl+Enter</span>
        </div>
      </form>

      {error && (
        <p role="alert">
          {errorText(error)}
          {error === "LLM_NOT_CONFIGURED" && (
            <>
              {" "}
              <Link to="/settings">{t("memory.goToSettings")}</Link>
            </>
          )}
        </p>
      )}
      {run && (
        <div className="memory-result">
          {statusText(run.status) && (
            <p role="status" aria-live="polite" data-testid="memory-status">
              {statusText(run.status)}
              {run.status === "failed" && run.error && has(MEMORY_ERRORS, run.error) && ` ${errorText(run.error)}`}
            </p>
          )}
          {run.status === "empty" && reasonText(run.result?.reason) && (
            <p data-testid="memory-reason">{reasonText(run.result?.reason)}</p>
          )}
          {run.result?.answer && (
            <div data-testid="memory-answer">
              <p className="answer">{run.result.answer}</p>
              <h2>{t("memory.sources")}</h2>
              <ol className="sources">
                {run.result.sources.map((source: Source) => (
                  <li key={`${source.meeting_id}-${source.segment_id}`}>
                    <Link to={sourceLink(source)}>
                      {source.meeting_title} · {sourceWhen(source)}
                    </Link>
                    {source.track !== "notes" && (
                      <span className="meta">
                        {" "}
                        · {source.person ?? source.speaker ?? t("meeting.noSpeaker")} · {source.language ?? "?"}
                      </span>
                    )}
                    <blockquote>{source.text}</blockquote>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {!run.result?.answer && (run.result?.retrieved?.length ?? 0) > 0 && (
            <div data-testid="memory-retrieved">
              <h2>{t("memory.fragments")}</h2>
              <ol className="sources">
                {run.result!.retrieved!.map((chunk: Retrieved, index) => (
                  <li key={`${chunk.meeting_id}-${chunk.start}-${index}`}>
                    {chunk.segment_id ? (
                      <Link to={sourceLink({ ...chunk, segment_id: chunk.segment_id })}>
                        {chunk.meeting_title} · {sourceWhen({ ...chunk, segment_id: chunk.segment_id })}
                      </Link>
                    ) : (
                      <span>
                        {chunk.meeting_title} · {formatTimestamp(chunk.start)}
                      </span>
                    )}
                    {chunk.track !== "notes" && (chunk.speaker !== undefined || chunk.language !== undefined) && (
                      <span className="meta">
                        {" "}
                        · {chunk.person ?? chunk.speaker ?? t("meeting.noSpeaker")} · {chunk.language ?? "?"}
                      </span>
                    )}
                    {chunk.content && <blockquote>{chunk.content}</blockquote>}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
      <ConceptGraphSection />
    </section>
  );
}
