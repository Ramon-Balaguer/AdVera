import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { z } from "zod";

import { ApiError, describeError } from "../../api";
import { formatDate } from "../../format";
import { ConceptGraphSection } from "../brain/ConceptGraphSection";
import { relationLabel, typeLabel } from "../brain/conceptGraphApi";
import { FACT_KINDS } from "../brain/factsApi";

// Everything the Brain holds of this meeting (ADR 0024): the index, the facts of its summary,
// the concepts and relationships found in it, its tags and the people named as its speakers.
const jobSchema = z.object({
  state: z.enum(["none", "queued", "running", "completed", "failed"]),
  error: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  up_to_date: z.boolean().nullable().optional(),
});
const reach = { other_meetings: z.number(), first_seen: z.string().nullable().optional() };
const brainSchema = z.object({
  meeting_id: z.string(),
  title: z.string(),
  date: z.string(),
  index: jobSchema.extend({ chunks: z.number(), embedded: z.number() }),
  projection: jobSchema,
  fact_counts: z.record(z.string(), z.number()),
  concepts: z.array(z.object({ id: z.string(), name: z.string(), type: z.string(), mentions: z.number(), ...reach })),
  relationships: z.array(
    z.object({
      source_id: z.string(),
      source: z.string(),
      target_id: z.string(),
      target: z.string(),
      type: z.string(),
      evidence: z.number(),
    }),
  ),
  tags: z.array(z.object({ id: z.string(), label: z.string(), ...reach })),
  people: z.array(z.object({ id: z.string(), name: z.string(), speakers: z.array(z.string()), ...reach })),
});

async function fetchMeetingBrain(meetingId: string) {
  const response = await fetch(`/api/meetings/${meetingId}/brain`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `HTTP_${response.status}`);
  return brainSchema.parse(body);
}

// How far something goes beyond this meeting: where else it appears, and since when.
function Reach({ item }: { item: { other_meetings: number; first_seen?: string | null } }) {
  const { t } = useTranslation();
  if (item.other_meetings === 0) return <span data-testid="reach-none">{t("meetingBrain.onlyHere")}</span>;
  return (
    <span data-testid="reach">
      {t("meetingBrain.alsoIn", { count: item.other_meetings })}
      {item.first_seen && ` ${t("meetingBrain.since", { date: formatDate(item.first_seen, "medium") })}`}
    </span>
  );
}

export function MeetingBrain({ meetingId }: { meetingId: string }) {
  const { t } = useTranslation();
  const brain = useQuery({
    queryKey: ["meeting-brain", meetingId],
    queryFn: () => fetchMeetingBrain(meetingId),
    refetchInterval: (query) => {
      const data = query.state.data;
      // While something is still being read, ask again.
      return data && (data.index.state === "queued" || data.index.state === "running" || data.projection.state === "queued" || data.projection.state === "running") ? 5_000 : false;
    },
  });

  if (brain.isPending) return <p role="status">{t("common.loading")}</p>;
  if (brain.isError) {
    return <p role="alert">{describeError(brain.error instanceof ApiError ? brain.error.code : null)}</p>;
  }
  const data = brain.data;
  const factCount = FACT_KINDS.reduce((sum, kind) => sum + (data.fact_counts[kind] ?? 0), 0);
  const notice =
    data.projection.state === "none"
      ? t("meetingBrain.notProjected")
      : data.projection.up_to_date === false
        ? t("meetingBrain.outOfDate")
        : null;

  return (
    <section className="meeting-brain" aria-label={t("meetingBrain.region")} data-testid="meeting-brain">
      <h2>{t("meetingBrain.title")}</h2>

      <h3>{t("meetingBrain.index")}</h3>
      <p data-testid="brain-index">
        <span className={`state state-job-${data.index.state === "none" ? "queued" : data.index.state}`}>
          {t(`meetingBrain.indexState.${data.index.state}`)}
        </span>{" "}
        {data.index.chunks > 0 && t("meetingBrain.chunks", { count: data.index.chunks, embedded: data.index.embedded })}
        {data.index.completed_at && <span className="meta"> · {formatDate(data.index.completed_at, "medium")}</span>}
        {data.index.error && <span className="hint"> {describeError(data.index.error)}</span>}
        {data.index.up_to_date === false && data.index.state !== "none" && (
          <span className="hint"> {t("meetingBrain.indexOutOfDate")}</span>
        )}
      </p>
      {notice && (
        <p className="hint" role="status" data-testid="brain-notice">
          {notice}
        </p>
      )}

      <h3>{t("meetingBrain.facts")}</h3>
      <p data-testid="brain-facts">
        {factCount === 0 ? (
          t("meetingBrain.noFacts")
        ) : (
          <Link to={`/brain/facts?meeting=${meetingId}`}>{t("meetingBrain.factsLink", { count: factCount })}</Link>
        )}{" "}
        <Link to="/brain/facts">{t("meetingBrain.allFactsLink")}</Link>
      </p>

      <h3>{t("meetingBrain.concepts")}</h3>
      {data.concepts.length === 0 ? (
        <p className="hint">{t("meetingBrain.noConcepts")}</p>
      ) : (
        <ul className="concept-list" data-testid="meeting-concepts">
          {data.concepts.map((concept) => (
            <li key={concept.id}>
              <Link to={`/brain/timeline/${concept.id}`}>{concept.name}</Link>{" "}
              <span className="meta">
                {typeLabel(concept.type)} · {t("meetingBrain.mentions", { count: concept.mentions })} ·{" "}
                <Reach item={concept} />
              </span>
            </li>
          ))}
        </ul>
      )}

      {data.relationships.length > 0 && (
        <>
          <h3>{t("meetingBrain.relationships")}</h3>
          <ul className="relationship-list" data-testid="meeting-relationships">
            {data.relationships.map((item) => (
              <li key={`${item.source_id}-${item.type}-${item.target_id}`}>
                {item.source} <span className="meta">{relationLabel(item.type)}</span> {item.target}
              </li>
            ))}
          </ul>
        </>
      )}

      {data.tags.length > 0 && (
        <>
          <h3>{t("meetingBrain.tags")}</h3>
          <ul>
            {data.tags.map((tag) => (
              <li key={tag.id}>
                <Link to={`/brain/timeline/${tag.id}`}>{tag.label}</Link>{" "}
                <span className="meta">
                  <Reach item={tag} />
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {data.people.length > 0 && (
        <>
          <h3>{t("meetingBrain.people")}</h3>
          <ul>
            {data.people.map((person) => (
              <li key={person.id}>
                <Link to={`/brain/timeline/${person.id}`}>{person.name}</Link>{" "}
                <span className="meta">
                  {person.speakers.join(", ")} · <Reach item={person} />
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      <details className="meeting-brain-graph">
        <summary>{t("meetingBrain.graph")}</summary>
        <ConceptGraphSection meetingId={meetingId} />
      </details>
    </section>
  );
}
