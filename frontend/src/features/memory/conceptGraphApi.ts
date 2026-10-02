import { z } from "zod";

import { ApiError } from "../../api";
import i18n from "../../i18n";

// Contracts mirror backend/app/concept_graph_api.py (read-only; ADR 0019).
export const CONCEPT_TYPES = ["topic", "person", "organization", "project", "product", "technology", "tag"] as const;

/** A concept type in the interface language. */
export function typeLabel(type: string): string {
  return (CONCEPT_TYPES as readonly string[]).includes(type)
    ? i18n.t(`conceptType.${type as (typeof CONCEPT_TYPES)[number]}`)
    : type;
}

export const TYPE_COLORS: Record<string, string> = {
  topic: "#6366f1",
  person: "#d97706",
  organization: "#0d9488",
  project: "#db2777",
  product: "#2563eb",
  technology: "#16a34a",
  tag: "#64748b",
};

const RELATIONS = [
  "related_to",
  "depends_on",
  "part_of",
  "decided_by",
  "assigned_to",
  "constrains",
  "derived_from",
  "verifies",
] as const;

/** A relationship type in the interface language ("is part of"). */
export function relationLabel(type: string): string {
  return (RELATIONS as readonly string[]).includes(type) ? i18n.t(`relation.${type as (typeof RELATIONS)[number]}`) : type;
}

const nodeSchema = z.object({
  id: z.string(),
  type: z.string(),
  label: z.string(),
  meetings: z.number(),
  mentions: z.number(),
  is_tag: z.boolean(),
});
const edgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  type: z.string(),
  source_type: z.string(),
  occurrences: z.number(),
  meetings: z.number(),
});
export const graphSchema = z.object({
  state: z.enum(["empty", "partial", "ready"]),
  nodes: z.array(nodeSchema),
  edges: z.array(edgeSchema),
  total_nodes: z.number(),
  truncated: z.boolean(),
  hidden_isolated: z.number().default(0),
});
export type ConceptGraphData = z.infer<typeof graphSchema>;
export type GraphNode = z.infer<typeof nodeSchema>;

const evidenceSchema = z.object({
  segment_id: z.string(),
  start: z.number().nullable(), // a note block has no time (ADR 0020)
  text: z.string().nullable(),
  track: z.string().nullable().optional(),
});
export const detailSchema = z.object({
  id: z.string(),
  type: z.string(),
  label: z.string(),
  is_tag: z.boolean(),
  aliases: z.array(z.string()),
  meetings: z.array(
    z.object({
      meeting_id: z.string(),
      title: z.string(),
      created_at: z.string(),
      mention: z.string().nullable(),
      evidence: z.array(evidenceSchema),
      tagged: z.boolean(),
      spoke: z.boolean().default(false), // a speaker of the meeting is this person (ADR 0021)
    }),
  ),
  relations: z.array(
    z.object({
      id: z.string(),
      direction: z.enum(["outgoing", "incoming"]),
      type: z.string(),
      source_type: z.string(),
      other_id: z.string(),
      other_label: z.string(),
      other_type: z.string(),
      meetings: z.array(z.string()),
      evidence: z.array(evidenceSchema),
    }),
  ),
});
export type ConceptDetail = z.infer<typeof detailSchema>;

async function get<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `HTTP_${response.status}`);
  }
  return schema.parse(await response.json());
}

export interface GraphFilters {
  type: string;
  q: string;
  tag: string;
  includeIsolated: boolean;
}

export const fetchConceptGraph = (filters: GraphFilters) => {
  const params = new URLSearchParams();
  if (filters.type) params.set("type", filters.type);
  if (filters.q) params.set("q", filters.q);
  if (filters.tag) params.set("tag", filters.tag);
  if (!filters.includeIsolated) params.set("include_isolated", "false");
  return get(`/api/memory/concept-graph?${params.toString()}`, graphSchema);
};

export const fetchConceptDetail = (id: string) => get(`/api/memory/concepts/${id}`, detailSchema);
