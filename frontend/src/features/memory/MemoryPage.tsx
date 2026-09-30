import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { z } from "zod";

import { api } from "../../api";
import { formatTimestamp } from "../../format";
import { ConceptGraphSection } from "./ConceptGraphSection";
import { sourceLink } from "./links";

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

const STATUS: Record<QueryRun["status"], string> = {
  queued: "En cola…",
  retrieving: "Buscando en las reuniones…",
  synthesizing: "Redactando la respuesta…",
  completed: "",
  empty: "No hay evidencia suficiente en las reuniones para responder.",
  failed: "La consulta falló.",
};

const REASONS: Record<string, string> = {
  NO_MATCH: "La búsqueda no encontró ningún fragmento parecido a la pregunta. Revisa los filtros de idioma y fechas o prueba con otras palabras.",
  NO_SEGMENTS: "Se encontraron fragmentos, pero sus segmentos ya no están en la transcripción definitiva de la reunión.",
  MODEL_INSUFFICIENT: "El modelo leyó los fragmentos encontrados y consideró que no contienen la respuesta. Puedes revisarlos debajo.",
  UNCITED: "El modelo respondió sin citar fragmentos válidos, así que su respuesta no se muestra. Los fragmentos encontrados están debajo.",
  INVALID_ANSWER: "El modelo devolvió una respuesta que no se pudo leer. Los fragmentos encontrados están debajo.",
};

const OVERVIEW: Record<string, string> = {
  empty: "Todavía no hay reuniones indexadas.",
  indexing: "Indexando reuniones…",
  partial: "Índice parcial: la búsqueda semántica no está disponible para todo el contenido.",
  ready: "",
};

const ERRORS: Record<string, string> = {
  LLM_NOT_CONFIGURED: "Configura el servidor y el modelo LLM en Ajustes.",
  LLM_UNAVAILABLE: "No se pudo contactar con el servidor LLM; se muestran los fragmentos encontrados.",
  QUEUE_UNAVAILABLE: "El sistema de colas no está disponible. Inténtalo más tarde.",
};

function wsUrl(path: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${path}`;
}

export { sourceLink };

// The last search (form + summary + sources) lives in the browser so that coming back from a
// meeting with the browser's back button shows it again, pre-filled, to open other references.
const STORAGE_KEY = "advera.memory.search";
const TERMINAL = ["completed", "empty", "failed"];
const savedSchema = z.object({
  question: z.string(),
  language: z.string(),
  dateFrom: z.string(),
  dateTo: z.string(),
  tag: z.string().default(""),
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
  const overview = useQuery({
    queryKey: ["memory-overview"],
    queryFn: async () => overviewSchema.parse(await (await fetch("/api/memory/overview")).json()),
    refetchInterval: 15_000,
  });
  const [saved] = useState(loadSaved);
  const [question, setQuestion] = useState(saved?.question ?? "");
  const [language, setLanguage] = useState(saved?.language ?? "");
  const [tag, setTag] = useState(saved?.tag ?? "");
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.listTags });
  const [dateFrom, setDateFrom] = useState(saved?.dateFrom ?? "");
  const [dateTo, setDateTo] = useState(saved?.dateTo ?? "");
  const [run, setRun] = useState<QueryRun | null>(saved?.run ?? null);
  const [error, setError] = useState<string | null>(null);
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => () => socket.current?.close(), []);

  useEffect(() => {
    try {
      const value: Saved = { question, language, dateFrom, dateTo, tag, run };
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch {
      // Storage may be unavailable or full; the search still works, it is just not remembered.
    }
  }, [question, language, dateFrom, dateTo, tag, run]);

  const follow = (queryId: string) => {
    socket.current?.close();
    const ws = new WebSocket(wsUrl(`/ws/query/${queryId}`));
    socket.current = ws;
    ws.onmessage = (message) => {
      const event = JSON.parse(String(message.data));
      if (event.type === "query.state") setRun(querySchema.parse(event));
    };
    ws.onclose = async () => {
      // HTTP is the durable recovery path if the socket drops before a terminal state.
      const response = await fetch(`/api/memory/query/${queryId}`);
      if (response.ok) setRun(querySchema.parse(await response.json()));
    };
  };

  useEffect(() => {
    if (saved?.run && !TERMINAL.includes(saved.run.status)) follow(saved.run.query_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (question.trim().length < 2) return;
    setError(null);
    const filters: Record<string, string> = {};
    if (language) filters.language = language;
    if (tag) filters.tag = tag;
    if (dateFrom) filters.date_from = `${dateFrom}T00:00:00Z`;
    if (dateTo) filters.date_to = `${dateTo}T23:59:59Z`;
    const response = await fetch("/api/memory/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question.trim(), filters }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : "HTTP_ERROR");
      return;
    }
    const created = querySchema.parse(body);
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
      <h1>Memoria</h1>
      {data && (
        <p className="hint" data-testid="memory-overview">
          {data.meetings_indexed} reuniones indexadas · {data.chunks} fragmentos · {data.embedded_chunks} con embeddings
          {OVERVIEW[data.state] && ` · ${OVERVIEW[data.state]}`}
        </p>
      )}
      <form className="memory-form" onSubmit={submit}>
        <label htmlFor="memory-question">¿Qué quieres saber de tus reuniones?</label>
        <textarea
          id="memory-question"
          rows={3}
          value={question}
          maxLength={500}
          placeholder="¿Qué decidimos sobre las copias de seguridad?"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="row">
          <label>
            Idioma{" "}
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="">Todos</option>
              <option value="ca">Català</option>
              <option value="es">Español</option>
              <option value="en">English</option>
            </select>
          </label>
          {(tags.data?.length ?? 0) > 0 && (
            <label>
              Etiqueta{" "}
              <select
                value={tag}
                onChange={(event) => setTag(event.target.value)}
                aria-label="Filtrar la búsqueda por etiqueta"
              >
                <option value="">Todas</option>
                {tags.data!.map((item) => (
                  <option key={item.concept_id} value={item.label}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Desde <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label>
            Hasta <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
          <button type="submit" disabled={busy || question.trim().length < 2}>
            Preguntar
          </button>
          <span className="meta">Ctrl+Enter</span>
        </div>
      </form>

      {error && (
        <p role="alert">
          {ERRORS[error] ?? `Error (${error}).`}
          {error === "LLM_NOT_CONFIGURED" && (
            <>
              {" "}
              <Link to="/settings">Ir a Ajustes</Link>
            </>
          )}
        </p>
      )}
      {run && (
        <div className="memory-result">
          {STATUS[run.status] && (
            <p role="status" aria-live="polite" data-testid="memory-status">
              {STATUS[run.status]}
              {run.status === "failed" && run.error && ` ${ERRORS[run.error] ?? ""}`}
            </p>
          )}
          {run.status === "empty" && run.result?.reason && REASONS[run.result.reason] && (
            <p data-testid="memory-reason">{REASONS[run.result.reason]}</p>
          )}
          {run.result?.answer && (
            <div data-testid="memory-answer">
              <p className="answer">{run.result.answer}</p>
              <h2>Fuentes</h2>
              <ol className="sources">
                {run.result.sources.map((source: Source) => (
                  <li key={`${source.meeting_id}-${source.segment_id}`}>
                    <Link to={sourceLink(source)}>
                      {source.meeting_title} · {formatTimestamp(source.start)}
                    </Link>
                    <span className="meta">
                      {" "}
                      · {source.speaker ?? "Hablante no disponible"} · {source.language ?? "?"}
                    </span>
                    <blockquote>{source.text}</blockquote>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {!run.result?.answer && (run.result?.retrieved?.length ?? 0) > 0 && (
            <div data-testid="memory-retrieved">
              <h2>Fragmentos encontrados</h2>
              <ol className="sources">
                {run.result!.retrieved!.map((chunk: Retrieved, index) => (
                  <li key={`${chunk.meeting_id}-${chunk.start}-${index}`}>
                    {chunk.segment_id ? (
                      <Link to={sourceLink({ ...chunk, segment_id: chunk.segment_id })}>
                        {chunk.meeting_title} · {formatTimestamp(chunk.start)}
                      </Link>
                    ) : (
                      <span>
                        {chunk.meeting_title} · {formatTimestamp(chunk.start)}
                      </span>
                    )}
                    {(chunk.speaker !== undefined || chunk.language !== undefined) && (
                      <span className="meta">
                        {" "}
                        · {chunk.speaker ?? "Hablante no disponible"} · {chunk.language ?? "?"}
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
