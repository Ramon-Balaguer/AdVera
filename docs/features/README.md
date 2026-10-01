# Feature memory

This directory is the durable product memory for AdVera features.

The Product Owner creates one new Markdown record for every feature. Existing records are historical and must not be reused for a different feature:

- before technical planning, with the discovery brief and acceptance criteria;
- after implementation, by completing that feature's own file with the actual status, files, validation, risks and next action.

Feature records are factual project documentation. They do not replace tests, ADRs or API documentation, and must not contain secrets, production credentials, real meeting content or chain-of-thought.

The canonical end-to-end recorded-meeting flow lives in [Meeting Processing Flow](../meeting-processing-flow.md). Update it together with any change to processing stages, providers, states, provenance or persistence boundaries.

## Template

```markdown
# Feature: <name>
Status: planned | in progress | partial | complete | blocked
Last updated: YYYY-MM-DD

## Objective
## Scope
## Acceptance criteria
## Implementation state
## Decisions
## Files changed
## Validation
## Risks
## Next action
```

The header block must appear directly under the title, in that order. `Status` accepts only the five values above; `Last updated` is an ISO date.

Additional sections are allowed and are not deprecated by omission. A record that changes transcript authority, provenance, a provider role, job states or a failure boundary must keep that content: write it inside `Implementation state` or `Decisions` rather than dropping it to satisfy the template. Losing architectural content to gain template conformance is a regression, not a fix.

There is no fixed `Owner` field. Ownership follows the role that did the work under [the agent workflow](../agent-workflow.md); the authoring agent is recorded in the task or pull request instead.

## Records

136 feature records, most recently updated first.

| Feature | Status | Last updated |
|---|---|---|
| [Rebuild meeting notes and @references](rebuild-meeting-notes.md) | complete | 2026-10-01 |
| [Rebuild speakers named as people](rebuild-speaker-people.md) | complete | 2026-10-01 |
| [Rebuild deletion of several meetings at once](rebuild-bulk-meeting-deletion.md) | complete | 2026-10-01 |
| [Rebuild tags at meeting creation and search by several tags](rebuild-tags-at-creation-and-multi-tag-search.md) | complete | 2026-10-01 |
| [Rebuild concept graph navigation](rebuild-concept-graph-navigation.md) | complete | 2026-10-01 |
| [Rebuild streamed LLM answers](rebuild-llm-streaming.md) | complete | 2026-10-01 |
| [Rebuild concept names in the output language](rebuild-concept-names-in-output-language.md) | in progress | 2026-10-01 |
| [Spike on local typed-decision models (Laya, tev1)](rebuild-local-decision-model-spike.md) | in progress | 2026-09-30 |
| [Rebuild QA and security hardening](rebuild-qa-security-hardening.md) | complete | 2026-09-30 |
| [Rebuild transcript that follows playback](rebuild-transcript-follows-playback.md) | complete | 2026-09-30 |
| [Rebuild synchronized playback of every track](rebuild-synced-multitrack-playback.md) | complete | 2026-09-30 |
| [Rebuild measured progress inside a track](rebuild-in-track-transcription-progress.md) | complete | 2026-09-30 |
| [Rebuild concept graph and manual tags](rebuild-concept-graph-and-tags.md) | complete | 2026-10-01 |
| [Rebuild Memory indexing and cited Q&A](rebuild-memory-retrieval.md) | complete | 2026-09-30 |
| [Rebuild Brain extraction](rebuild-brain-extraction.md) | partial | 2026-09-30 |
| [Rebuild settings page and LLM provider](rebuild-settings-and-llm-provider.md) | partial | 2026-09-30 |
| [Rebuild live capture waveforms per track](rebuild-live-capture-waveforms.md) | complete | 2026-09-30 |
| [Rebuild per-segment language detection for mixed-language tracks](rebuild-per-segment-language-detection.md) | partial | 2026-09-30 |
| [Rebuild desktop Capture Agent](rebuild-desktop-capture-agent.md) | partial | 2026-09-30 |
| [Rebuild browser microphone capture](rebuild-browser-microphone-capture.md) | partial | 2026-09-30 |
| [Rebuild local speaker diarization](rebuild-local-diarization.md) | partial | 2026-09-30 |
| [Rebuild Catalan in every test set](rebuild-catalan-test-coverage.md) | complete | 2026-09-30 |
| [Rebuild imported media keeps audio only](rebuild-import-audio-only.md) | complete | 2026-09-30 |
| [Rebuild import to definitive transcript](rebuild-import-definitive-transcript.md) | partial | 2026-09-30 |
| [Rebuild bootstrap and governance](rebuild-bootstrap-and-governance.md) | partial | 2026-09-30 |
| [Project baseline and current capabilities](project-baseline.md) | complete | 2026-09-30 |
| [MOSS Startup Cache and Prefetch](moss-startup-cache.md) | complete | 2026-09-30 |
| [MOSS persistent Hugging Face token](moss-persistent-huggingface-token.md) | complete | 2026-09-30 |
| [Meeting Free-Text Tags and Memory Concepts](meeting-free-text-tags-memory-concepts.md) | partial | 2026-09-30 |
| [Local startup database readiness](local-startup-database-readiness.md) | complete | 2026-09-30 |
| [One-off forced language for meeting reprocessing](forced-reprocess-language.md) | partial | 2026-09-30 |
| [Brain tag filter](brain-tag-filter.md) | complete | 2026-09-30 |
| [Asynchronous Transcription on Meeting Close](async-transcription-on-meeting-close.md) | partial | 2026-09-30 |
| [Backend worker console processing logs](backend-worker-console-lifecycle-logs.md) | partial | 2026-09-28 |
| [Original-language transcription](original-language-transcription.md) | complete | 2026-09-27 |
| [MOSS rejection diagnostics and fallback visibility](moss-fallback-diagnostics.md) | complete | 2026-09-27 |
| [Transcription Worker MOSS Readiness](transcription-worker-moss-readiness.md) | complete | 2026-09-26 |
| [Post-recording playback controls only](post-recording-playback-controls-only.md) | complete | 2026-09-26 |
| [New meeting state isolation on create](new-meeting-state-isolation-on-create.md) | in progress | 2026-09-26 |
| [MOSS Definitive Transcription Provider](moss-definitive-provider.md) | partial | 2026-09-26 |
| [Monitor Memory Job Repair](monitor-memory-job-repair.md) | complete | 2026-09-26 |
| [Memory worker completion summary](memory-worker-completion-summary.md) | partial | 2026-09-26 |
| [Memory index queue hot-loop prevention](memory-index-queue-hot-loop.md) | complete | 2026-09-26 |
| [Idempotent memory evidence retries](memory-evidence-idempotent-retry.md) | complete | 2026-09-26 |
| [Idempotent memory chunk retries](memory-chunk-idempotent-retry.md) | complete | 2026-09-26 |
| [Meeting media import](meeting-media-import.md) | complete | 2026-09-26 |
| [Meeting attendee count accuracy](meeting-attendee-count-accuracy.md) | complete | 2026-09-26 |
| [Header record/import navigation focus](header-record-import-focus.md) | complete | 2026-09-26 |
| [Frontend API Health Gate](frontend-api-health-gate.md) | complete | 2026-09-26 |
| [Development Workers and MOSS Startup](development-workers-moss-startup.md) | complete | 2026-09-26 |
| [Capture Agent Direct Backend PCM](capture-agent-direct-backend-pcm.md) | partial | 2026-09-26 |
| [Brain Worker Redis Reconnect](brain-worker-redis-reconnect.md) | complete | 2026-09-26 |
| [Brain worker LLM provider parity](brain-worker-llm-provider-parity.md) | complete | 2026-09-26 |
| [Brain output language selection regression](brain-output-language-selection-regression.md) | complete | 2026-09-26 |
| [Brain Concept Relationship Alias Resolution](brain-concept-relationship-alias-resolution.md) | complete | 2026-09-26 |
| [vLLM AMD and NVIDIA Runtime Selection](vllm-amd-nvidia-runtime-selection.md) | complete | 2026-09-25 |
| [Redis Queue Monitor](redis-queue-monitor.md) | complete | 2026-09-25 |
| [Monitor Pending Job Highlight](monitor-pending-job-highlight.md) | complete | 2026-09-25 |
| [Monitor Job Error Reason](monitor-job-error-reason.md) | complete | 2026-09-25 |
| [Meeting Reprocess Includes Definitive Transcription](meeting-reprocess-transcription.md) | complete | 2026-09-25 |
| [Local development console mode](local-development-console-mode.md) | complete | 2026-09-25 |
| [Interface language and LLM response language](interface-language-and-llm-response-language.md) | complete | 2026-09-25 |
| [Incremental transcription worker progress](incremental-transcription-worker-progress.md) | complete | 2026-09-25 |
| [Historical Memory Backfill](historical-memory-backfill.md) | partial | 2026-09-25 |
| [Brain Validation Failure Diagnostics](brain-validation-failure-diagnostics.md) | in progress | 2026-09-25 |
| [Brain job schema drift recovery](brain-job-schema-drift.md) | complete | 2026-09-25 |
| [Architecture Decision Records](architecture-decision-records.md) | complete | 2026-09-25 |
| [Alembic schema ownership](alembic-schema-ownership.md) | complete | 2026-09-25 |
| [Capture Lock After Memory](capture-lock-after-memory.md) | partial | 2026-09-23 |
| [Speaker diarization quality](speaker-diarization-quality.md) | complete | 2026-09-22 |
| [Post-recording failure classification](post-recording-failure-classification.md) | complete | 2026-09-22 |
| [Meeting Deletion Data Retention](meeting-deletion-data-retention.md) | complete | 2026-10-01 |
| [Local speaker diarization without Hugging Face](local-speaker-diarization.md) | in progress | 2026-09-22 |
| [Incremental Development Scripts](incremental-development-scripts.md) | complete | 2026-09-22 |
| [Global Concept Graph](concept-graph.md) | partial | 2026-09-22 |
| [Brain Session Tabs Without Horizontal Scroll](brain-session-tabs-no-horizontal-scroll.md) | partial | 2026-09-22 |
| [Brain Filter Select Styling](brain-filter-select-styling.md) | partial | 2026-09-22 |
| [System Monitor](system-monitor.md) | complete | 2026-09-21 |
| [Settings frontend feature](settings-feature.md) | in progress | 2026-09-21 |
| [PostgreSQL-Native Hybrid Memory Search](postgresql-native-hybrid-memory-search.md) | partial | 2026-09-21 |
| [Persistent runtime settings](persistent-runtime-settings.md) | complete | 2026-09-21 |
| [Ollama settings group](ollama-settings-group.md) | complete | 2026-09-21 |
| [Ollama model auto-discovery on settings load](ollama-settings-auto-discovery.md) | complete | 2026-09-21 |
| [Meetings list frontend feature](meetings-list-feature.md) | in progress | 2026-09-21 |
| [Meeting view frontend feature](meeting-view-feature.md) | in progress | 2026-09-21 |
| [Hugging Face token usage and download logs](huggingface-download-logging.md) | complete | 2026-09-21 |
| [Frontend feature boundaries](frontend-feature-boundaries.md) | complete | 2026-09-21 |
| [English page names](english-page-names.md) | complete | 2026-09-21 |
| [Alineación de evidencias en consultas Brain](brain-evidence-segment-alignment.md) | complete | 2026-09-21 |
| [Persistent Hugging Face token settings](persistent-huggingface-token-settings.md) | complete | 2026-09-20 |
| [OpenAPI Contract and QA Gate](openapi-contract-and-qa-gate.md) | partial | 2026-09-20 |
| [Memory Embeddings Provider](memory-embeddings-provider.md) | partial | 2026-09-20 |
| [Reliable Brain Search Results via WebSocket](brain-query-results-websocket.md) | complete | 2026-09-20 |
| [Backend statement coverage to 90%](backend-statement-coverage-90.md) | partial | 2026-09-20 |
| [Agent code coverage to 90%](agent-code-coverage-90.md) | partial | 2026-09-20 |
| [Actualizacion de WhisperX y Lightning](whisperx-lightning-update.md) | complete | 2026-09-19 |
| [Tray local traffic diagnostics](tray-send-statistics.md) | complete | 2026-09-19 |
| [Transcript scrollbar polish](transcript-scrollbar-polish.md) | complete | 2026-09-19 |
| [TorchCodec ASR migration](torchcodec-asr-migration.md) | complete | 2026-09-19 |
| [WebSocket de métricas del sistema](system-metrics-websocket.md) | partial | 2026-09-19 |
| [Intervalo de actualización de system-metrics](system-metrics-refresh-interval.md) | partial | 2026-09-19 |
| [Configuracion de Ollama](settings-ollama-url.md) | complete | 2026-09-19 |
| [Per-track PCM WebSockets](per-track-pcm-websockets.md) | complete | 2026-09-19 |
| [Outbound capture agent WebSocket](outbound-capture-agent-websocket.md) | complete | 2026-09-19 |
| [Conectividad y seleccion de modelos Ollama](ollama-connectivity-model-selection.md) | complete | 2026-09-19 |
| [Biblioteca de reuniones](meeting-library.md) | partial | 2026-09-19 |
| [Live summary observability](live-summary-observability.md) | complete | 2026-09-19 |
| [Frontend capture-agent proxy migration](frontend-capture-agent-proxy-migration.md) | complete | 2026-09-19 |
| [Definitive transcription progress](definitive-transcription-progress.md) | complete | 2026-09-19 |
| [Brain & Memoria global](brain-memoria-global.md) | partial | 2026-09-19 |
| [Brain extraction from definitive transcript](brain-extraction-from-definitive-transcript.md) | complete | 2026-09-19 |
| [Audio WebSocket close safety](audio-websocket-close-safety.md) | complete | 2026-09-19 |
| [ASR runtime warnings](asr-runtime-warnings.md) | complete | 2026-09-19 |
| [Agent PCM E2E delivery fix](agent-pcm-e2e-delivery-fix.md) | complete | 2026-09-19 |
| [Transcript card review UI](transcript-card-review-ui.md) | complete | 2026-09-18 |
| [NVIDIA CUDA runtime for ASR](nvidia-cuda-asr-runtime.md) | complete | 2026-09-18 |
| [Live meeting summary](live-meeting-summary.md) | complete | 2026-09-18 |
| [Definitive transcription segment language](definitive-transcription-segment-language.md) | complete | 2026-09-18 |
| [Definitive transcription language](definitive-transcription-language.md) | complete | 2026-09-18 |
| [Bug: audio-metrics response regression](audio-metrics-400-regression.md) | complete | 2026-09-18 |
| [Windows WASAPI loopback system track](windows-wasapi-loopback-system-track.md) | complete | 2026-09-17 |
| [Windows agent tray and autostart](windows-agent-tray-autostart.md) | in progress | 2026-09-17 |
| [WhisperX compatibility with PyTorch 2.6+](whisperx-pytorch26-compatibility.md) | complete | 2026-09-17 |
| [VAD, windowing and transcript stitching](vad-windowing-and-transcript-stitching.md) | in progress | 2026-09-17 |
| [Transcription relay reconnection fix](transcription-relay-reconnection-fix.md) | complete | 2026-09-17 |
| [Stable audio pipeline with provisional and definitive transcript](stable-audio-transcription-pipeline.md) | in progress | 2026-09-17 |
| [Separate live and definitive ASR models](separate-live-definitive-asr-models.md) | complete | 2026-09-17 |
| [QA release gate](qa-release-gate.md) | blocked | 2026-09-17 |
| [Native dual-track audio agent](native-dual-track-audio-agent.md) | partial | 2026-09-17 |
| [Frontend audio reconnection](frontend-audio-reconnection.md) | in progress | 2026-09-17 |
| [Frontend audio reconnection E2E coverage](frontend-audio-reconnection-e2e.md) | complete | 2026-09-17 |
| [Dual-track playback and live capture metrics](dual-track-playback-live-metrics.md) | in progress | 2026-09-17 |
| [Audio session reconnection](audio-session-reconnection.md) | in progress | 2026-09-17 |
| [Agent recording notification](agent-recording-notification.md) | complete | 2026-09-17 |
| [Agent microphone waveform](agent-microphone-waveform.md) | in progress | 2026-09-17 |
| [Agent configuration wizard](agent-configuration-wizard.md) | in progress | 2026-09-17 |
