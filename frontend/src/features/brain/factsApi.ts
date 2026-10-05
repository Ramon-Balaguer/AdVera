import { z } from "zod";

import { ApiError } from "../../api";

// Facts of the meetings (ADR 0024): decisions, actions, risks, open questions and topics.
export const FACT_KINDS = ["decision", "action", "question", "risk", "topic"] as const;
export type FactKind = (typeof FACT_KINDS)[number];
export const DECISION_STATES = ["proposed", "decided", "rejected", "superseded", "unknown"] as const;

const citationSchema = z.object({
  segment_id: z.string(),
  start: z.number().nullable().optional(),
  track: z.string().nullable().optional(),
  text: z.string().nullable().optional(),
});
export const factSchema = z.object({
  id: z.string(),
  kind: z.enum(FACT_KINDS),
  text: z.string(),
  state: z.string().nullable().optional(),
  owner: z.string().nullable().optional(),
  due_date: z.string().nullable().optional(),
  evidence: z.array(citationSchema),
  meeting_id: z.string(),
  meeting_title: z.string(),
  meeting_date: z.string(),
});
export type Fact = z.infer<typeof factSchema>;

const factsSchema = z.object({
  total: z.number(),
  counts: z.record(z.string(), z.number()),
  facts: z.array(factSchema),
});

export interface FactFilters {
  kind: FactKind;
  state: string;
  owner: string;
  q: string;
  tags: string[];
  dateFrom: string;
  dateTo: string;
  limit: number;
}

export async function fetchFacts(filters: FactFilters) {
  const params = new URLSearchParams({ kind: filters.kind, limit: String(filters.limit) });
  if (filters.state && filters.kind === "decision") params.set("state", filters.state);
  if (filters.owner && filters.kind === "action") params.set("owner", filters.owner);
  if (filters.q) params.set("q", filters.q);
  for (const tag of filters.tags) params.append("tag", tag);
  if (filters.dateFrom) params.set("date_from", `${filters.dateFrom}T00:00:00Z`);
  if (filters.dateTo) params.set("date_to", `${filters.dateTo}T23:59:59Z`);
  const response = await fetch(`/api/brain/facts?${params.toString()}`);
  if (!response.ok) throw new ApiError(response.status, `HTTP_${response.status}`);
  return factsSchema.parse(await response.json());
}
