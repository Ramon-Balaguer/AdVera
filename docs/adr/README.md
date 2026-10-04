# Architecture Decision Records

ADRs capture decisions that change AdVera's ownership boundaries, contracts, persistent data model, provider integrations or deployment/recovery behavior. Feature records remain the place for implementation details, acceptance criteria and test evidence.

Every ADR carries a `## Status` heading directly below its title. The Status column below reproduces that heading verbatim; do not shorten it, because the qualifiers carry real constraints.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-bge-m3-pgvector-brain.md) | BGE-M3 and PostgreSQL/pgvector brain retrieval | Accepted for the first Summary & Brain architecture/data slice |
| [0002](0002-definitive-transcript-source-of-truth.md) | Definitive transcript as the intelligence boundary | Accepted |
| [0003](0003-asr-provider-boundary-and-moss-role.md) | ASR provider boundary and MOSS definitive role | Accepted |
| [0004](0004-audio-capture-and-live-delivery.md) | Audio capture and live delivery contracts | Accepted |
| [0005](0005-dual-track-audio-processing.md) | Independent microphone and system tracks | Accepted |
| [0006](0006-reprocess-transcript-before-summary.md) | Reprocess transcript before Summary | Accepted; partially superseded by ADR 0008 (reprocessing runs as a durable asynchronous TranscriptionJob, not inside the HTTP request) |
| [0007](0007-moss-vllm-development-deployment.md) | MOSS vLLM development deployment | Accepted for local development and canary evaluation; production enablement pending |
| [0008](0008-asynchronous-definitive-transcription-worker.md) | Asynchronous definitive transcription worker | Accepted |
| [0009](0009-summary-output-language-provenance.md) | Summary output language provenance | Accepted (2026-09-25) |
| [0010](0010-capture-agent-direct-backend-pcm.md) | Capture Agent direct backend PCM ownership | Accepted |
| [0011](0011-derived-meeting-attendee-count.md) | Derived meeting attendee count | Accepted (2026-09-26) |
| [0012](0012-external-media-import.md) | External media import uses the system track | Accepted (2026-09-26); partially superseded by ADR 0016 (the uploaded file is not retained) |
| [0013](0013-manual-meeting-tags-brain-concepts.md) | Manual meeting tags are shared brain concepts with explicit assignments | Accepted (2026-09-26) |
| [0014](0014-original-language-transcription.md) | Preserve original-language transcription and defer translations to derived artifacts | Accepted |
| [0015](0015-authentication-deferred-single-user.md) | Authentication deferred; single-user API without login | Accepted (2026-09-30) |
| [0016](0016-imported-media-keeps-audio-only.md) | Imported media keeps only the extracted audio | Accepted (2026-09-30) |
| [0017](0017-meeting-unique-speaker-labels.md) | Speaker labels are unique within a meeting across tracks | Accepted (2026-09-30) |
| [0018](0018-per-chunk-language-detection-provider.md) | faster-whisper provider with per-chunk language detection | Accepted (2026-10-01, operator review; proposed 2026-09-30). It is the default definitive provider in this rebuild. |
| [0019](0019-summary-concept-extraction-and-graph-projection.md) | Summary concept extraction and concept graph projection | Accepted (2026-10-01, operator review; proposed 2026-09-30, revised 2026-10-01) |
| [0020](0020-meeting-notes-and-references-as-citable-annex.md) | Meeting notes and @references as a citable annex to the transcript | Proposed (2026-10-01); a new capability the documentation does not cover. Awaits human review. |
| [0021](0021-speakers-named-as-people.md) | Speakers named as people of a shared directory | Proposed (2026-10-01); a new capability the documentation does not cover. Awaits human review. |
| [0022](0022-brain-and-summary-naming.md) | Brain is the knowledge of all the meetings; Summary is what is extracted from one | Accepted (2026-10-04), by the operator, for commercial reasons. |

New ADRs should link back to the feature record that motivated them and to any superseded decision. Do not create ADRs for isolated UI styling, test-only changes or local refactors without a durable boundary change.

The canonical recorded-meeting process is documented in [Meeting Processing Flow](../meeting-processing-flow.md). Changes to that flow must update the diagram in the same change.
