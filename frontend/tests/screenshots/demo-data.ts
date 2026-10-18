// Demo data for the README and landing-page screenshots. Every name, meeting and quote here is
// fictitious; nothing comes from a real recording.

export const LAUNCH = "a1000000-0000-4000-8000-000000000001";
export const SYNC = "a1000000-0000-4000-8000-000000000002";
export const INTERVIEW = "a1000000-0000-4000-8000-000000000003";
export const INFRA = "a1000000-0000-4000-8000-000000000004";
export const DESIGN = "a1000000-0000-4000-8000-000000000005";
export const RETRO = "a1000000-0000-4000-8000-000000000006";
export const BUDGET = "a1000000-0000-4000-8000-000000000007";
export const SECURITY = "a1000000-0000-4000-8000-000000000008";
export const ONE_ON_ONE = "a1000000-0000-4000-8000-000000000009";

const tag = (id: string, label: string) => ({ assignment_id: `as-${id}-${label}`, concept_id: `tag-${label}`, label });

function meeting(
  id: string,
  title: string,
  created: string,
  duration: number,
  languages: string[],
  attendees: number,
  tags: string[],
  status = "ready",
) {
  return {
    id,
    title,
    description: null,
    status,
    started_at: created,
    ended_at: created,
    duration,
    primary_language: languages,
    created_by: null,
    created_at: created,
    updated_at: created,
    attendee_count: attendees,
    tracks: ["microphone", "system"],
    tags: tags.map((label) => tag(id, label)),
  };
}

export const MEETINGS = [
  meeting(ONE_ON_ONE, "1:1 Marta / Jordi", "2026-10-16T16:00:00Z", 1520, ["ca"], 2, ["People"], "processing"),
  meeting(LAUNCH, "Launch planning · AdVera Cloud v2", "2026-10-15T09:30:00Z", 2538, ["en", "es", "ca"], 4, ["Launch", "Roadmap"]),
  meeting(SYNC, "Weekly product sync", "2026-10-13T10:00:00Z", 1865, ["ca", "es"], 5, ["Weekly", "Roadmap"]),
  meeting(INTERVIEW, "Customer interview · logistics pilot", "2026-10-09T15:00:00Z", 2710, ["en"], 3, ["Research", "Customer"]),
  meeting(INFRA, "Revisión de infraestructura: almacenamiento y copias", "2026-10-07T11:00:00Z", 3320, ["es"], 4, ["Infrastructure"]),
  meeting(DESIGN, "Design critique · onboarding flow", "2026-10-06T14:30:00Z", 2290, ["en"], 4, ["Design", "Launch"]),
  meeting(RETRO, "Retrospectiva sprint 41", "2026-10-03T09:00:00Z", 2840, ["ca"], 6, ["Retro"]),
  meeting(BUDGET, "Presupuesto 2027 · arranque", "2026-10-01T12:00:00Z", 3900, ["es", "en"], 5, ["Budget", "Roadmap"]),
  meeting(SECURITY, "Security review with the external auditors", "2026-09-29T10:00:00Z", 4115, ["en"], 4, ["Security", "Customer"]),
];

export const TAGS = [
  { concept_id: "tag-Roadmap", label: "Roadmap", meetings: 3 },
  { concept_id: "tag-Launch", label: "Launch", meetings: 2 },
  { concept_id: "tag-Customer", label: "Customer", meetings: 2 },
  { concept_id: "tag-Weekly", label: "Weekly", meetings: 1 },
  { concept_id: "tag-Research", label: "Research", meetings: 1 },
  { concept_id: "tag-Infrastructure", label: "Infrastructure", meetings: 1 },
  { concept_id: "tag-Design", label: "Design", meetings: 1 },
  { concept_id: "tag-Retro", label: "Retro", meetings: 1 },
  { concept_id: "tag-Budget", label: "Budget", meetings: 1 },
  { concept_id: "tag-Security", label: "Security", meetings: 1 },
  { concept_id: "tag-People", label: "People", meetings: 1 },
];

// The hero meeting: a multilingual launch-planning call, mic and system tracks.
const seg = (i: number, start: number, end: number, person: string, speaker: string, language: string, text: string, track = "system") => ({
  id: `${track}-${String(i).padStart(5, "0")}`,
  start,
  end,
  text,
  track,
  language,
  speaker,
  person,
});

export const LAUNCH_SEGMENTS = [
  seg(1, 4.2, 13.8, "Marta Vidal", "SPEAKER_00", "en", "Okay, let's get going. The goal today is to lock the scope and the date for Cloud v2, so marketing can start on Monday.", "microphone"),
  seg(2, 14.5, 24.1, "Jordi Puig", "SPEAKER_01", "en", "From engineering, the import pipeline and the meeting bot are done. The only open item is the Teams admission flow."),
  seg(3, 25.0, 36.7, "Jordi Puig", "SPEAKER_01", "es", "Si dejamos Teams para la 2.1, podemos congelar el código el 4 de noviembre sin problema."),
  seg(4, 37.9, 47.2, "Aisha Okafor", "SPEAKER_02", "en", "I'd rather ship without Teams than ship a flaky admission screen. First impressions matter here."),
  seg(5, 48.0, 58.4, "Marta Vidal", "SPEAKER_00", "en", "Agreed. So the decision is: Google Meet only for launch, Teams follows in 2.1.", "microphone"),
  seg(6, 59.6, 71.3, "Lucas Moreau", "SPEAKER_03", "en", "That works for the campaign. I need the final screenshots by October 28 to build the landing page."),
  seg(7, 72.1, 83.9, "Aisha Okafor", "SPEAKER_02", "ca", "Jo me n'encarrego. Tindré les captures i el vídeo curt llestos el dimecres 28."),
  seg(8, 85.0, 97.6, "Jordi Puig", "SPEAKER_01", "es", "Un riesgo: la migración de pgvector en clientes con más de cien mil fragmentos tarda casi una hora."),
  seg(9, 98.4, 108.2, "Marta Vidal", "SPEAKER_00", "en", "Can we run it in the background and keep the app usable while it indexes?", "microphone"),
  seg(10, 109.0, 121.5, "Jordi Puig", "SPEAKER_01", "es", "Sí, con el worker del Brain en segundo plano. Lo documento en las notas de la versión."),
  seg(11, 122.8, 134.0, "Lucas Moreau", "SPEAKER_03", "en", "What about pricing for the managed tier? Sales keeps asking and we still don't have an answer."),
  seg(12, 135.1, 144.9, "Marta Vidal", "SPEAKER_00", "en", "That's still open. Let's bring it to the budget meeting next week with real numbers.", "microphone"),
  seg(13, 146.2, 158.0, "Aisha Okafor", "SPEAKER_02", "ca", "També caldria revisar l'onboarding en català i castellà abans del llançament."),
  seg(14, 159.3, 170.6, "Marta Vidal", "SPEAKER_00", "en", "Good point. Launch date stays November 12, code freeze November 4. Thanks everyone.", "microphone"),
];

const ev = (i: number, track = "system") => {
  const s = LAUNCH_SEGMENTS.find((x) => x.id === `${track}-${String(i).padStart(5, "0")}`)!;
  return { segment_id: s.id, start: s.start, end: s.end, speaker: s.person, track: s.track };
};

export const LAUNCH_SUMMARY = {
  meeting_id: LAUNCH,
  state: "completed",
  llm_configured: true,
  job: { status: "completed", model: "qwen3:32b", language: "en", error: null, attempts: 1 },
  result: {
    summary: {
      text:
        "The team locked the scope of Cloud v2: it launches on November 12 with Google Meet support only, and Microsoft Teams moves to 2.1. Code freeze is November 4. Marketing gets final screenshots on October 28. The pgvector migration will run in the background, and pricing for the managed tier goes to next week's budget meeting.",
      evidence: [ev(5, "microphone"), ev(14, "microphone"), ev(6)],
    },
    decisions: [
      { text: "Launch with Google Meet only; Microsoft Teams moves to version 2.1", state: "decided", evidence: [ev(5, "microphone"), ev(4)] },
      { text: "Launch date November 12, code freeze November 4", state: "decided", evidence: [ev(14, "microphone"), ev(3)] },
      { text: "Run the pgvector migration in the background with the Brain worker", state: "decided", evidence: [ev(10)] },
    ],
    actions: [
      { text: "Deliver final screenshots and a short product video", owner: "Aisha Okafor", due_date: "Oct 28", evidence: [ev(7)] },
      { text: "Document the background migration in the release notes", owner: "Jordi Puig", due_date: null, evidence: [ev(10)] },
      { text: "Review onboarding in Catalan and Spanish before launch", owner: "Aisha Okafor", due_date: "Nov 4", evidence: [ev(13)] },
    ],
    topics: [
      { text: "Launch scope and date", evidence: [ev(1, "microphone")] },
      { text: "Meeting bot platforms", evidence: [ev(2)] },
    ],
    open_questions: [{ text: "Pricing of the managed tier", evidence: [ev(11), ev(12, "microphone")] }],
    risks: [{ text: "The pgvector migration takes almost an hour above 100k chunks", evidence: [ev(8)] }],
  },
};

export const LAUNCH_SPEAKERS = {
  speakers: [
    { track: "microphone", speaker: "SPEAKER_00", seconds: 512, segments: 38, sample: "Okay, let's get going.", person: "Marta Vidal", concept_id: "p-marta" },
    { track: "system", speaker: "SPEAKER_01", seconds: 803, segments: 51, sample: "From engineering, the import pipeline…", person: "Jordi Puig", concept_id: "p-jordi" },
    { track: "system", speaker: "SPEAKER_02", seconds: 611, segments: 40, sample: "I'd rather ship without Teams…", person: "Aisha Okafor", concept_id: "p-aisha" },
    { track: "system", speaker: "SPEAKER_03", seconds: 402, segments: 22, sample: "That works for the campaign.", person: "Lucas Moreau", concept_id: "p-lucas" },
  ],
  analysis: null,
};

export const PEOPLE = [
  { concept_id: "p-marta", name: "Marta Vidal", meetings: 8 },
  { concept_id: "p-jordi", name: "Jordi Puig", meetings: 7 },
  { concept_id: "p-aisha", name: "Aisha Okafor", meetings: 5 },
  { concept_id: "p-lucas", name: "Lucas Moreau", meetings: 4 },
];

export const LAUNCH_NOTES = [
  "## Before the call",
  "- Confirm the **code freeze** with engineering",
  "- Ask Lucas what the campaign needs from us",
  "",
  "## Takeaways",
  `- Teams waits for 2.1: [@Launch planning · 00:48](/meetings/${LAUNCH}?segment=microphone-00005)`,
  `- Pricing still open, follow up in [@Presupuesto 2027 · arranque](/meetings/${BUDGET})`,
  "- Onboarding copy needs a pass in **ca** and **es**",
].join("\n");

export const LAUNCH_BRAIN = {
  meeting_id: LAUNCH,
  title: "Launch planning · AdVera Cloud v2",
  date: "2026-10-15T09:30:00Z",
  index: { state: "completed", error: null, completed_at: "2026-10-15T10:20:00Z", up_to_date: true, chunks: 64, embedded: 64 },
  projection: { state: "completed", error: null, completed_at: "2026-10-15T10:21:00Z", up_to_date: true },
  fact_counts: { decision: 3, action: 3, question: 1, risk: 1, topic: 2 },
  concepts: [
    { id: "c-bot", name: "Meeting bot", type: "product", mentions: 6, other_meetings: 3, first_seen: "2026-09-12T10:00:00Z" },
    { id: "c-teams", name: "Microsoft Teams", type: "product", mentions: 5, other_meetings: 2, first_seen: "2026-09-18T10:00:00Z" },
    { id: "c-pgvector", name: "pgvector", type: "technology", mentions: 4, other_meetings: 2, first_seen: "2026-10-07T11:00:00Z" },
    { id: "c-pricing", name: "Managed tier pricing", type: "topic", mentions: 3, other_meetings: 1, first_seen: "2026-10-01T12:00:00Z" },
    { id: "c-onboarding", name: "Onboarding", type: "topic", mentions: 2, other_meetings: 1, first_seen: "2026-10-06T14:30:00Z" },
    { id: "c-campaign", name: "Launch campaign", type: "project", mentions: 3, other_meetings: 0, first_seen: "2026-10-15T09:30:00Z" },
  ],
  relationships: [
    { source_id: "c-teams", source: "Microsoft Teams", target_id: "c-bot", target: "Meeting bot", type: "part_of", evidence: 2 },
    { source_id: "c-pgvector", source: "pgvector", target_id: "c-campaign", target: "Launch campaign", type: "constrains", evidence: 1 },
    { source_id: "c-campaign", source: "Launch campaign", target_id: "c-onboarding", target: "Onboarding", type: "depends_on", evidence: 1 },
  ],
  tags: [
    { id: "tag-Launch", label: "Launch", other_meetings: 1, first_seen: "2026-10-06T14:30:00Z" },
    { id: "tag-Roadmap", label: "Roadmap", other_meetings: 2, first_seen: "2026-10-01T12:00:00Z" },
  ],
  people: [
    { id: "p-marta", name: "Marta Vidal", speakers: ["SPEAKER_00"], other_meetings: 7, first_seen: "2026-09-02T10:00:00Z" },
    { id: "p-jordi", name: "Jordi Puig", speakers: ["SPEAKER_01"], other_meetings: 6, first_seen: "2026-09-02T10:00:00Z" },
    { id: "p-aisha", name: "Aisha Okafor", speakers: ["SPEAKER_02"], other_meetings: 4, first_seen: "2026-09-08T10:00:00Z" },
    { id: "p-lucas", name: "Lucas Moreau", speakers: ["SPEAKER_03"], other_meetings: 3, first_seen: "2026-09-15T10:00:00Z" },
  ],
};

// The global Brain: a cited answer across meetings.
export const BRAIN_OVERVIEW = {
  state: "ready",
  meetings_indexed: 72,
  chunks: 4813,
  embedded_chunks: 4813,
  jobs_pending: 0,
  jobs_failed: 0,
  llm_configured: true,
};

export const BRAIN_QUESTION = "Why did we postpone Microsoft Teams support?";

export const BRAIN_ANSWER = {
  query_id: "demo-query",
  query: BRAIN_QUESTION,
  status: "completed",
  error: null,
  result: {
    answer:
      "Teams support was moved to version 2.1 because its admission flow was the only unfinished part of the meeting bot [1]. Aisha argued that shipping a flaky admission screen would hurt first impressions [2], and Marta made the call to launch with Google Meet only [3]. Leaving Teams out lets engineering freeze the code on November 4 [4]. The Teams admission issue had already been raised in the weekly product sync [5].",
    retrieval: "hybrid",
    retrieved: [],
    sources: [
      { meeting_id: LAUNCH, meeting_title: "Launch planning · AdVera Cloud v2", meeting_date: "2026-10-15T09:30:00Z", segment_id: "system-00002", start: 14.5, end: 24.1, speaker: "SPEAKER_01", person: "Jordi Puig", track: "system", language: "en", text: LAUNCH_SEGMENTS[1].text },
      { meeting_id: LAUNCH, meeting_title: "Launch planning · AdVera Cloud v2", meeting_date: "2026-10-15T09:30:00Z", segment_id: "system-00004", start: 37.9, end: 47.2, speaker: "SPEAKER_02", person: "Aisha Okafor", track: "system", language: "en", text: LAUNCH_SEGMENTS[3].text },
      { meeting_id: LAUNCH, meeting_title: "Launch planning · AdVera Cloud v2", meeting_date: "2026-10-15T09:30:00Z", segment_id: "microphone-00005", start: 48.0, end: 58.4, speaker: "SPEAKER_00", person: "Marta Vidal", track: "microphone", language: "en", text: LAUNCH_SEGMENTS[4].text },
      { meeting_id: LAUNCH, meeting_title: "Launch planning · AdVera Cloud v2", meeting_date: "2026-10-15T09:30:00Z", segment_id: "system-00003", start: 25.0, end: 36.7, speaker: "SPEAKER_01", person: "Jordi Puig", track: "system", language: "es", text: LAUNCH_SEGMENTS[2].text },
      { meeting_id: SYNC, meeting_title: "Weekly product sync", meeting_date: "2026-10-13T10:00:00Z", segment_id: "system-00031", start: 742.3, end: 751.0, speaker: "SPEAKER_02", person: "Jordi Puig", track: "system", language: "ca", text: "La pantalla d'admissió de Teams encara falla una de cada cinc vegades." },
    ],
  },
};

// The concept graph: concepts, people, projects and tags tied by relationships.
const node = (id: string, type: string, label: string, meetings: number, mentions: number) => ({
  id, type, label, meetings, mentions, is_tag: type === "tag",
});
const edge = (source: string, target: string, type: string, meetings = 1) => ({
  id: `${source}-${target}`, source, target, type, source_type: type === "related_to" ? "manual_user" : "summary", occurrences: meetings, meetings,
});

const CORE_GRAPH = {
  state: "ready",
  total_nodes: 30,
  truncated: false,
  hidden_isolated: 0,
  nodes: [
    node("c-advera-cloud", "product", "AdVera Cloud v2", 6, 31),
    node("c-bot", "product", "Meeting bot", 4, 18),
    node("c-teams", "product", "Microsoft Teams", 3, 11),
    node("c-meet", "product", "Google Meet", 3, 9),
    node("c-brain", "product", "Brain", 5, 22),
    node("c-pgvector", "technology", "pgvector", 3, 10),
    node("c-postgres", "technology", "PostgreSQL", 4, 12),
    node("c-redis", "technology", "Redis Streams", 3, 8),
    node("c-whisper", "technology", "Whisper large-v3", 3, 9),
    node("c-backups", "technology", "Backups", 2, 7),
    node("c-gpu", "technology", "GPU workers", 2, 5),
    node("c-campaign", "project", "Launch campaign", 2, 8),
    node("c-onboarding", "project", "Onboarding redesign", 3, 12),
    node("c-pilot", "project", "Logistics pilot", 2, 9),
    node("c-audit", "project", "Security audit", 2, 7),
    node("c-pricing", "topic", "Managed tier pricing", 3, 10),
    node("c-budget", "topic", "Budget 2027", 2, 9),
    node("c-freeze", "topic", "Code freeze", 2, 5),
    node("c-i18n", "topic", "Localization", 3, 6),
    node("c-retention", "topic", "Data retention", 2, 6),
    node("c-hiring", "topic", "Hiring", 2, 4),
    node("p-marta", "person", "Marta Vidal", 8, 14),
    node("p-jordi", "person", "Jordi Puig", 7, 12),
    node("p-aisha", "person", "Aisha Okafor", 5, 9),
    node("p-lucas", "person", "Lucas Moreau", 4, 6),
    node("o-north", "organization", "Northbridge Freight", 2, 7),
    node("o-auditors", "organization", "External auditors", 1, 4),
    node("tag-Launch", "tag", "Launch", 2, 0),
    node("tag-Roadmap", "tag", "Roadmap", 3, 0),
    node("tag-Security", "tag", "Security", 1, 0),
  ],
  edges: [
    edge("c-bot", "c-advera-cloud", "part_of", 3),
    edge("c-brain", "c-advera-cloud", "part_of", 4),
    edge("c-teams", "c-bot", "part_of", 2),
    edge("c-meet", "c-bot", "part_of", 2),
    edge("c-brain", "c-pgvector", "depends_on", 2),
    edge("c-pgvector", "c-postgres", "part_of", 2),
    edge("c-brain", "c-redis", "depends_on"),
    edge("c-whisper", "c-gpu", "depends_on", 2),
    edge("c-advera-cloud", "c-whisper", "depends_on"),
    edge("c-backups", "c-postgres", "verifies"),
    edge("c-campaign", "c-advera-cloud", "derived_from"),
    edge("c-campaign", "c-onboarding", "depends_on"),
    edge("c-onboarding", "c-i18n", "related_to"),
    edge("c-freeze", "c-advera-cloud", "constrains", 2),
    edge("c-pgvector", "c-freeze", "constrains"),
    edge("c-pricing", "c-advera-cloud", "related_to", 2),
    edge("c-pricing", "c-budget", "part_of"),
    edge("c-hiring", "c-budget", "part_of"),
    edge("c-pilot", "o-north", "related_to", 2),
    edge("c-pilot", "c-bot", "depends_on"),
    edge("c-audit", "o-auditors", "related_to"),
    edge("c-audit", "c-retention", "verifies"),
    edge("c-retention", "c-backups", "constrains"),
    edge("c-freeze", "p-jordi", "assigned_to"),
    edge("c-campaign", "p-lucas", "assigned_to"),
    edge("c-onboarding", "p-aisha", "assigned_to"),
    edge("c-teams", "p-marta", "decided_by"),
    edge("c-pricing", "p-marta", "assigned_to"),
    edge("c-gpu", "p-jordi", "assigned_to"),
    edge("tag-Launch", "c-advera-cloud", "related_to"),
    edge("tag-Roadmap", "c-pricing", "related_to"),
    edge("tag-Security", "c-audit", "related_to"),
  ],
};

export const TEAMS_DETAIL = {
  id: "c-teams",
  type: "product",
  label: "Microsoft Teams",
  is_tag: false,
  aliases: ["Teams", "MS Teams"],
  meetings: [
    {
      meeting_id: LAUNCH, title: "Launch planning · AdVera Cloud v2", created_at: "2026-10-15T09:30:00Z", mention: "Teams", tagged: false,
      evidence: [{ segment_id: "microphone-00005", start: 48.0, text: LAUNCH_SEGMENTS[4].text }],
    },
    {
      meeting_id: SYNC, title: "Weekly product sync", created_at: "2026-10-13T10:00:00Z", mention: "Teams", tagged: false,
      evidence: [{ segment_id: "system-00031", start: 742.3, text: "La pantalla d'admissió de Teams encara falla una de cada cinc vegades." }],
    },
    { meeting_id: INTERVIEW, title: "Customer interview · logistics pilot", created_at: "2026-10-09T15:00:00Z", mention: "Microsoft Teams", tagged: false, evidence: [] },
  ],
  relations: [
    { id: "c-teams-c-bot", direction: "outgoing", type: "part_of", source_type: "summary", other_id: "c-bot", other_label: "Meeting bot", other_type: "product", meetings: ["Launch planning · AdVera Cloud v2", "Weekly product sync"], evidence: [] },
    { id: "c-teams-p-marta", direction: "outgoing", type: "decided_by", source_type: "summary", other_id: "p-marta", other_label: "Marta Vidal", other_type: "person", meetings: ["Launch planning · AdVera Cloud v2"], evidence: [] },
  ],
};

// A concept's timeline across meetings.
export const PRICING_TIMELINE = {
  concept_id: "c-pricing",
  label: "Managed tier pricing",
  type: "topic",
  is_tag: false,
  truncated: false,
  entries: [
    {
      meeting_id: LAUNCH, title: "Launch planning · AdVera Cloud v2", date: "2026-10-15T09:30:00Z", mentioned: true, tagged: false, spoke: false,
      quotes: [{ segment_id: "system-00011", start: 122.8, track: "system", text: LAUNCH_SEGMENTS[10].text }],
      facts: [{ kind: "question", text: "Pricing of the managed tier", state: null, owner: null, due_date: null,
        evidence: [{ segment_id: "system-00011", start: 122.8, track: "system", text: LAUNCH_SEGMENTS[10].text }] }],
      summary: null,
    },
    {
      meeting_id: SYNC, title: "Weekly product sync", date: "2026-10-13T10:00:00Z", mentioned: true, tagged: false, spoke: false,
      quotes: [{ segment_id: "system-00044", start: 1210.5, track: "system", text: "Els clients del pilot pagarien per no haver de mantenir la GPU." }],
      facts: [{ kind: "action", text: "Collect what the pilot customers pay today for transcription", state: null, owner: "Lucas Moreau", due_date: "Oct 20",
        evidence: [{ segment_id: "system-00045", start: 1225.0, track: "system", text: "Lucas, pots recollir què paguen ara?" }] }],
      summary: null,
    },
    {
      meeting_id: BUDGET, title: "Presupuesto 2027 · arranque", date: "2026-10-01T12:00:00Z", mentioned: true, tagged: true, spoke: false,
      quotes: [{ segment_id: "system-00012", start: 402.0, track: "system", text: "El plan gestionado tiene que cubrir al menos el coste de las GPU." }],
      facts: [
        { kind: "decision", text: "The managed tier must at least cover GPU costs", state: "decided", owner: null, due_date: null,
          evidence: [{ segment_id: "system-00012", start: 402.0, track: "system", text: "El plan gestionado tiene que cubrir al menos el coste de las GPU." }] },
        { kind: "risk", text: "A price per seat may push small teams to self-host", state: null, owner: null, due_date: null,
          evidence: [{ segment_id: "note-003", start: null, track: "notes", text: "Per-seat pricing vs. small teams" }] },
      ],
      summary: null,
    },
  ],
};

// Decisions of every meeting.
const fact = (id: string, kind: string, text: string, m: (typeof MEETINGS)[number], start: number, extra: Record<string, unknown> = {}) => ({
  id, kind, text, state: kind === "decision" ? "decided" : null, owner: null, due_date: null,
  evidence: [{ segment_id: `system-${String(Math.round(start)).padStart(5, "0")}`, start, track: "system", text: "" }],
  meeting_id: m.id, meeting_title: m.title, meeting_date: m.created_at, ...extra,
});
const byId = (id: string) => MEETINGS.find((m) => m.id === id)!;

export const FACTS = {
  total: 8,
  counts: { decision: 8, action: 14, question: 5, risk: 4, topic: 19 },
  facts: [
    fact("f1", "decision", "Launch with Google Meet only; Microsoft Teams moves to version 2.1", byId(LAUNCH), 48),
    fact("f2", "decision", "Launch date November 12, code freeze November 4", byId(LAUNCH), 159.3),
    fact("f3", "decision", "Run the pgvector migration in the background with the Brain worker", byId(LAUNCH), 109),
    fact("f4", "decision", "Ship the Catalan onboarding copy before the Spanish one", byId(SYNC), 640.2, { state: "proposed" }),
    fact("f5", "decision", "Offer the logistics pilot a 60-day trial with the meeting bot", byId(INTERVIEW), 1802.5),
    fact("f6", "decision", "Move nightly backups to object storage with 30-day retention", byId(INFRA), 1190),
    fact("f7", "decision", "Replace the five-step wizard with a single setup screen", byId(DESIGN), 935.4),
    fact("f8", "decision", "The managed tier must at least cover GPU costs", byId(BUDGET), 402),
  ],
};

export const MONITOR = (() => {
  const names = ["transcription", "summary", "brain-index", "brain-query"];
  const avg: Record<string, number> = { transcription: 94, summary: 71, "brain-index": 18, "brain-query": 9 };
  const done: Record<string, number> = { transcription: 72, summary: 70, "brain-index": 72, "brain-query": 214 };
  return {
    generated_at: "2026-10-16T16:30:00+00:00",
    services: [
      { name: "api", ok: true, latency_ms: null },
      { name: "redis", ok: true, latency_ms: 1 },
      { name: "postgres", ok: true, latency_ms: 2 },
    ],
    llm: { configured: true, base_url: "http://llm.lan:11434", model: "qwen3:32b" },
    workers: names.map((name) => ({
      name,
      state: "up",
      instances: [{ host: "gpu-01", pid: 41, started_at: "2026-10-16T08:00:00+00:00", job_id: name === "transcription" ? "job-1" : null }],
      since: "2026-10-16T08:00:00+00:00",
    })),
    queues: names.map((name) => ({ name, state: "ok", stream_length: name === "transcription" ? 1 : 0, pending: name === "transcription" ? 1 : 0, lag: 0, consumers_gone: 0 })),
    jobs: names.map((name) => ({
      name,
      queued: 0,
      running: name === "transcription" ? 1 : 0,
      completed: done[name],
      failed: 0,
      oldest_queued_seconds: null,
      stale: 0,
      completed_last_hour: name === "brain-query" ? 6 : 1,
      average_seconds: avg[name],
      last_failures: [],
    })),
    recent: {
      transcription: [
        { id: "t1", status: "running", attempts: 1, max_attempts: 3, error: null, meeting_id: ONE_ON_ONE, title: "1:1 Marta / Jordi", created_at: "2026-10-16T16:26:00+00:00", duration_seconds: null },
        { id: "t2", status: "completed", attempts: 1, max_attempts: 3, error: null, meeting_id: LAUNCH, title: "Launch planning · AdVera Cloud v2", created_at: "2026-10-15T10:13:00+00:00", duration_seconds: 118 },
      ],
      summary: [
        { id: "s1", status: "completed", attempts: 1, max_attempts: 3, error: null, meeting_id: LAUNCH, title: "Launch planning · AdVera Cloud v2", created_at: "2026-10-15T10:15:00+00:00", duration_seconds: 84 },
        { id: "s2", status: "completed", attempts: 1, max_attempts: 3, error: null, meeting_id: SYNC, title: "Weekly product sync", created_at: "2026-10-13T10:40:00+00:00", duration_seconds: 66 },
      ],
      "brain-index": [
        { id: "b1", status: "completed", attempts: 1, max_attempts: 3, error: null, meeting_id: LAUNCH, title: "Launch planning · AdVera Cloud v2", created_at: "2026-10-15T10:17:00+00:00", duration_seconds: 21 },
      ],
      "brain-query": [
        { id: "q1", status: "completed", attempts: 1, max_attempts: 1, error: null, meeting_id: null, title: BRAIN_QUESTION, created_at: "2026-10-16T16:20:00+00:00", duration_seconds: 7 },
        { id: "q2", status: "completed", attempts: 1, max_attempts: 1, error: null, meeting_id: null, title: "What did the auditors ask about data retention?", created_at: "2026-10-16T15:02:00+00:00", duration_seconds: 9 },
      ],
    },
  };
})();

/** A short stereo-free WAV with a gentle, speech-like envelope, so the players have something to draw. */
export function wav(seconds: number, seed: number): Buffer {
  const rate = 8_000;
  const n = seconds * rate;
  const data = Buffer.alloc(n * 2);
  let phase = seed;
  for (let i = 0; i < n; i++) {
    const t = i / rate;
    const envelope = Math.max(0, Math.sin(t * 1.7 + seed) * Math.sin(t * 0.31 + seed * 2)) ** 2;
    phase += (2 * Math.PI * (140 + 40 * Math.sin(t * 3 + seed))) / rate;
    data.writeInt16LE(Math.round(envelope * 9000 * Math.sin(phase)), i * 2);
  }
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  return Buffer.concat([header, data]);
}

// A larger Brain: about 500 concepts grown around the core ones above, the way months of meetings
// fill the graph. Deterministic (seeded), so the screenshot is the same on every run.
function grownGraph() {
  let s = 20261018;
  const rand = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
  const pick = <T,>(items: T[]) => items[Math.floor(rand() * items.length)];

  const first = ["Ana", "Pau", "Nuria", "Carlos", "Elena", "Marc", "Sofia", "David", "Laia", "Hugo", "Irene", "Oriol", "Clara", "Iván", "Mireia", "Tomás", "Julia", "Arnau", "Noa", "Raúl", "Emma", "Pol", "Lucía", "Sergi", "Priya", "Kenji", "Amara", "Leo"];
  const last = ["Serra", "Ortega", "Font", "Navarro", "Rius", "Molina", "Costa", "Ramos", "Soler", "Vega", "Bosch", "Prat", "Gil", "Mora", "Sato", "Nwosu", "Patel", "Weber"];
  const areas = ["Billing", "Search", "Mobile app", "Desktop agent", "Calendar sync", "Permissions", "Exports", "Notifications", "Analytics", "Audio import", "Diarization", "Summaries", "Speaker naming", "Notes editor", "Tags", "Timeline", "Facts", "Settings", "Setup wizard", "Self-hosting", "Docs site", "Landing page", "Status page", "Support inbox", "Partner portal", "Data export", "Admin console", "Webhooks", "SSO", "Audit log"];
  const aspects = ["roadmap", "metrics", "migration", "rollout", "redesign", "costs", "bugs", "latency", "feedback", "pricing", "QA", "beta", "accessibility", "copy", "limits"];
  const tech = ["Kubernetes", "Docker Compose", "Nginx", "FastAPI", "React", "Vite", "TypeScript", "Python 3.12", "SQLAlchemy", "Alembic", "Celery", "Ollama", "llama.cpp", "vLLM", "BGE-M3", "ECAPA", "faster-whisper", "CUDA 12", "cuBLAS", "Cytoscape", "CodeMirror", "Playwright", "pytest", "Ruff", "GitHub Actions", "Grafana", "Prometheus", "Loki", "MinIO", "S3", "Hugging Face", "ONNX", "WebSockets", "WebRTC", "FFmpeg", "Opus codec", "Piper TTS", "SoundCard", "sounddevice", "Tailscale", "WireGuard", "Caddy", "Let's Encrypt", "OpenTelemetry", "Sentry", "Zod", "TanStack Query", "i18next", "pgBouncer", "Vexa"];
  const orgs = ["Northbridge Freight", "Lumen Health", "Atlas Mobility", "Cobalt Bank", "Verdant Energy", "Harbor Logistics", "Quill Legal", "Orbit Retail", "Pioneer Schools", "Summit Insurance", "Delta Clinics", "Nimbus Media", "Granite Labs", "Beacon Ventures", "Helix Biotech", "Meridian Hotels", "Polar Robotics", "Crescent Foods", "Ivory Publishing", "Keystone Council"];
  const projects = ["Q1 roadmap", "Q2 roadmap", "Q3 roadmap", "Cloud v2.1", "Cloud v3", "Teams admission", "Zoom support", "Offline mode", "Mobile beta", "Pricing page", "Partner program", "SOC 2 readiness", "GDPR review", "Hiring plan 2027", "Office move", "Customer advisory board", "Conference talk", "Docs rewrite", "Design system", "Performance week", "Bug bash", "Data retention policy", "Backup drill", "On-call rotation", "Release train"];
  const tags = ["Urgent", "Follow-up", "Board", "Sales", "Support", "Hiring", "Legal", "Ops", "Finance", "Marketing", "Engineering", "Product", "Q4", "2027"];

  const nodes = [...CORE_GRAPH.nodes];
  const edges = [...CORE_GRAPH.edges];
  const ids = new Set(nodes.map((n) => n.id));
  const add = (type: string, label: string) => {
    const id = `g-${type}-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    if (ids.has(id)) return null;
    ids.add(id);
    const meetings = 1 + Math.floor(rand() ** 3 * 9);
    nodes.push(node(id, type, label, meetings, meetings + Math.floor(rand() * 12)));
    return id;
  };

  const generated: string[] = [];
  for (const label of tech) { const id = add("technology", label); if (id) generated.push(id); }
  for (const label of orgs) { const id = add("organization", label); if (id) generated.push(id); }
  for (const label of projects) { const id = add("project", label); if (id) generated.push(id); }
  for (const label of tags) { const id = add("tag", label); if (id) generated.push(id); }
  for (const area of areas) { const id = add("product", area); if (id) generated.push(id); }
  while (nodes.length < 400) {
    const id = add("topic", `${pick(areas)} ${pick(aspects)}`);
    if (id) generated.push(id);
  }
  while (nodes.length < 500) {
    const id = add("person", `${pick(first)} ${pick(last)}`);
    if (id) generated.push(id);
  }

  // Each new concept hangs from one to three others, preferring the well connected ones, so the
  // graph grows hubs and clusters instead of a uniform mesh.
  const degree = new Map<string, number>();
  for (const e of edges) for (const end of [e.source, e.target]) degree.set(end, (degree.get(end) ?? 0) + 1);
  const relations = ["related_to", "part_of", "depends_on", "assigned_to", "constrains", "derived_from", "decided_by", "verifies"];
  const placed = nodes.filter((n) => !generated.includes(n.id)).map((n) => n.id);
  for (const id of generated) {
    const links = 1 + Math.floor(rand() ** 2 * 3);
    for (let k = 0; k < links; k++) {
      let target = pick(placed);
      for (let tries = 0; tries < 3; tries++) {
        const other = pick(placed);
        if ((degree.get(other) ?? 0) > (degree.get(target) ?? 0)) target = other;
      }
      if (target === id || edges.some((e) => e.source === id && e.target === target)) continue;
      edges.push(edge(id, target, pick(relations), 1 + Math.floor(rand() * 3)));
      for (const end of [id, target]) degree.set(end, (degree.get(end) ?? 0) + 1);
    }
    placed.push(id);
  }
  return { ...CORE_GRAPH, nodes, edges, total_nodes: nodes.length };
}

export const GRAPH = grownGraph();
