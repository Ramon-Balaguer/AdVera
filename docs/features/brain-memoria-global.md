# Feature: Brain & Memoria global
Status: partial
Last updated: 2026-09-19

## Problem and target user

El conocimiento generado por AdVera está actualmente aislado dentro de cada reunión. La página de **Brain & Memoria** debe permitir consultar el histórico de forma global, explorar las relaciones entre decisiones, tareas, personas, restricciones y conceptos, y volver siempre a la evidencia original.

Target user: una persona que revisa reuniones y necesita encontrar decisiones, entender su evolución y verificar cada respuesta en el transcript definitivo y en el audio. La primera versión asume un despliegue local single-user.

El diseño de referencia es `docs/design/brain_memoria_grafo_de_conocimiento_y_relaciones_sem_nticas/code.html`. Ese HTML define la jerarquía visual y el inventario de interacciones, pero no es una fuente de datos ni un contrato API.

## Desired outcome

El usuario puede realizar una consulta global sobre las reuniones procesadas y recibe una respuesta factual o una indicación explícita de que no existe evidencia suficiente. Las respuestas, nodos, relaciones y citas muestran su procedencia hasta reunión, segmento y timestamp de audio.

La experiencia incluye:

- Consola de consulta con filtros temporales, lingüísticos, por speaker y por tipo de entidad.
- Búsqueda híbrida full-text + vectorial.
- Respuesta RAG con citas verificadas.
- Grafo de conocimiento navegable e inspector de nodos.
- Evolución temporal de decisiones y relaciones de reemplazo.
- Métricas y estado real del índice.
- Navegación desde una evidencia global hasta la reunión y el audio correspondiente.

## Smallest useful increment

Una ruta `/brain` que consulte datos derivados de transcripts definitivos, permita buscar una decisión, muestre sus evidencias y abra la reunión correcta en el timestamp citado. El índice debe poder reconstruirse desde los datos canónicos y el frontend debe representar de forma honesta los estados vacío, indexando, parcial, listo y error.

## Scope

### In scope

- Contratos REST para overview, grafo, entidades, timeline, consultas y estados de jobs.
- Persistencia PostgreSQL + pgvector para chunks, embeddings, entidades, relaciones, evidencias, jobs y consultas.
- Embeddings locales BGE-M3 de 1024 dimensiones.
- Full-text search PostgreSQL complementario al retrieval vectorial.
- Indexación automática después de persistir un transcript definitivo.
- Proyección validada de conocimiento proveniente de Brain.
- Relaciones tipadas y regenerables: `supersedes`, `feeds`, `depends_on`, `decided_by`, `assigned_to`, `constrains`, `derived_from` y `verifies`.
- RAG asíncrono con contexto recuperado, respuesta estructurada y citas validadas.
- Página React integrada en la navegación actual.
- Navegación profunda hasta reunión, segmento y timestamp.
- Tests backend, integración PostgreSQL/pgvector, build frontend y E2E desktop/mobile.

### Out of scope

- Editar, fusionar o corregir manualmente memorias.
- Reindexado manual iniciado desde la interfaz.
- Exportación SVG/JSON desde la interfaz.
- Auditoría interactiva de prompts.
- Autenticación, RBAC, multiusuario y multi-tenant.
- Nuevas fuentes de audio o cambios en el pipeline ASR.
- Uso de transcript provisional o live summary para conocimiento, embeddings o respuestas.
- Migración completa a React Router o TanStack Query.
- Rediseño global del shell de AdVera.

## Acceptance criteria

1. La ruta `/brain` se integra con la navegación principal y conserva el shell visual actual de AdVera.
2. Una consulta global devuelve estados explícitos `queued`, `retrieving`, `synthesizing`, `completed`, `empty` o `failed`.
3. Una respuesta factual solo se presenta si sus citas pertenecen al contexto recuperado y apuntan a evidencia existente.
4. Cada cita contiene `meeting_id`, `segment_id`, timestamps, hash de entrada y metadata de procedencia suficiente para auditarla.
5. Una cita puede abrir la reunión correspondiente, seleccionar el segmento y reproducir el audio desde el timestamp.
6. Ningún transcript parcial/provisional puede crear chunks, embeddings, entidades, relaciones o respuestas consultables.
7. El grafo permite filtrar por texto, tipo, speaker, idioma, fecha y estado; seleccionar un nodo y ver su inspector.
8. Las relaciones tipadas sin evidencia válida, nodos huérfanos o segmentos desconocidos se rechazan.
9. Los embeddings se generan con BGE-M3 local y tienen exactamente 1024 dimensiones.
10. La búsqueda usa full-text y vector retrieval; los filtros se aplican antes de construir el contexto RAG.
11. La indexación y las consultas pesadas se ejecutan mediante jobs durables y no dentro de requests HTTP.
12. Los fallos del modelo, Redis o pgvector dejan un estado recuperable y no dañan el audio ni el transcript definitivo.
13. La interfaz funciona con teclado, tiene nombres accesibles, foco visible, estados anunciados y soporte para `Ctrl+Enter` y `Meta+Enter`.
14. El grafo y el inspector se apilan correctamente en móvil y no producen scroll horizontal.
15. No se muestran como datos reales los nombres, hashes, counts, reuniones o métricas hardcoded del HTML de diseño.
16. La migración funciona contra PostgreSQL con pgvector y la suite focalizada de backend, frontend y E2E pasa antes del handoff a QA/Security.

## States and failure behavior

- `empty`: no hay transcripts definitivos o no existe evidencia que responda a la consulta.
- `indexing`: hay transcripts definitivos pendientes de chunks, embeddings o proyección de conocimiento.
- `partial`: existe índice de transcript, pero Brain o la proyección del grafo aún no han terminado.
- `ready`: overview, retrieval y grafo disponibles según sus contratos.
- `queued`: job creado y pendiente de worker.
- `retrieving`: la consulta está ejecutando full-text/vector retrieval.
- `synthesizing`: el contexto fue recuperado y el proveedor está generando la respuesta estructurada.
- `completed`: respuesta validada con citas verificables.
- `failed`: error sanitizado y recuperable; no se presenta una respuesta como válida.
- Transcript inexistente, inválido o no definitivo: no se indexa y se informa el bloqueo.
- Proveedor de embeddings no disponible: se conserva full-text si está disponible y el índice queda parcial o fallido de forma explícita.
- Proveedor LLM no disponible: la recuperación puede permanecer disponible, pero no se inventa una síntesis.
- Evidencia de audio inexistente: se muestra la cita, pero el control de reproducción queda no disponible con explicación clara.
- Cambio del hash del transcript entre cola y ejecución: el job se invalida y debe reconciliarse con la nueva versión.
- Salida estructurada inválida: se rechaza, se reintenta según el contrato y nunca reemplaza una salida válida.

## Data and provenance constraints

- El transcript definitivo persistido es la única fuente de verdad para inteligencia.
- Audio original y transcript definitivo permanecen intactos aunque fallen Brain, embeddings, retrieval o LLM.
- Chunks, embeddings, entidades, relaciones y respuestas son datos derivados y regenerables.
- Cada derivado conserva meeting, segmento(s), timestamps, hash de entrada, versión de proyección y metadata de proveedor/modelo cuando corresponda.
- Las relaciones conservan evidencia propia; no se materializan relaciones especulativas como hechos.
- Las decisiones y acciones son ocurrencias trazables. Personas y conceptos pueden compartir una clave normalizada, pero no se fusionan silenciosamente.
- No se persiste ni se muestra chain-of-thought. Solo se guardan respuestas estructuradas, citas, hashes, metadata, estado y métricas permitidas.
- Tests y logs no contienen secretos, audio real ni contenido de reuniones reales.
- La UI no usa los datos de ejemplo del diseño como fallback de producción.

## Dependencies and assumptions

- PostgreSQL 16 con extensión pgvector ya está disponible mediante `pgvector/pgvector:pg16`.
- Redis Streams es el mecanismo de jobs existente y se reutilizará con colas independientes de `BrainJob`.
- Los transcripts definitivos se guardan actualmente como `transcript.json` bajo el almacenamiento de reuniones.
- Brain ya valida entradas definitivas, hashes y evidencias de segmentos; la nueva proyección se apoya en ese contrato.
- BGE-M3 se ejecuta localmente en el worker. La configuración debe permitir CPU como fallback explícito y documentado.
- La primera entrega es single-user local; auth/RBAC se abordará en una feature posterior.
- La navegación actual usa routing manual con `window.history`; la nueva ruta se incorporará sin una migración global.
- Se requiere un entorno PostgreSQL real para validar tipos vectoriales e índices HNSW; SQLite solo sirve para pruebas que no ejerciten SQL vectorial.

## Implementation plan

## ADRs

- [ADR 0001: BGE-M3 and PostgreSQL/pgvector memory retrieval](../adr/0001-bge-m3-pgvector-memory.md)
- [ADR 0002: Definitive transcript as the intelligence boundary](../adr/0002-definitive-transcript-source-of-truth.md)

### Phase 0: Product, architecture and contracts

1. Registrar esta feature antes de modificar backend o frontend.
2. Crear un ADR en `docs/adr/` para PostgreSQL + pgvector, BGE-M3, 1024 dimensiones, full-text complementario, cache local y embeddings regenerables.
3. Crear `backend/app/memory_contracts.py` con DTOs para overview, nodos, aristas, entidades, filtros, citas, timeline, jobs y consultas.
4. Fijar estos endpoints:
   - `GET /api/memory/overview`
   - `GET /api/memory/graph`
   - `GET /api/memory/entities/{entity_id}`
   - `GET /api/memory/timeline`
   - `POST /api/memory/query`
   - `GET /api/memory/query/{query_id}`
5. Definir límites de payload, máximo de nodos/aristas, top-k, tamaño de consulta y filtros soportados.

### Phase 1: Persistence and migration

1. Añadir a `backend/app/models.py` modelos separados de `BrainJob`: `MemoryIndexJob`, `MemoryEntity`, `MemoryRelationship`, `MemoryEvidence`, `MemoryChunk` y `MemoryQueryRun`.
2. Crear una migración posterior a `0002_create_brain_extraction.py` que habilite `vector`, cree tablas y añada claves foráneas.
3. En `MemoryChunk`, conservar texto derivado, `content_hash`, meeting, segmento, timestamps, idioma, speaker, `tsvector`, `vector(1024)`, modelo y estado.
4. Crear índices GIN para full-text, HNSW para distancia coseno y B-tree para meeting, fecha, idioma y tipo.
5. Añadir configuración de embedding, dimensión, dispositivo, batch, cache, colas y límites en `backend/app/config.py`.
6. Ajustar `backend/pyproject.toml`, `docker/compose.dev.yml` y `docker/compose.nvidia.yml` según el proveedor local y el worker.

### Phase 2: Indexing and graph projection

1. Implementar una interfaz y adaptador BGE-M3 en `backend/app/embeddings.py` o módulo equivalente. El modelo debe cargarse en el worker, usar batches y validar 1024 dimensiones.
2. Implementar indexación de chunks únicamente desde `TranscriptDocument.status=definitive`, preservando segmentos, speakers, idiomas y timestamps.
3. Implementar proyección de conocimiento desde resultados Brain validados.
4. Validar estrictamente nodos, aliases, estados, confianza, `source_segment_ids` y relaciones tipadas.
5. Crear `backend/app/memory_jobs.py` y `backend/app/memory_worker.py` con Redis Streams, idempotencia, leases, reintentos, recuperación stale y reconciliación.
6. Integrar `backend/app/audio.py` para encolar chunks después de persistir transcript definitivo y proyección después de Brain válido.
7. Implementar relaciones temporales como `supersedes`, `depends_on` y `constrains` solo cuando exista evidencia y confianza válidas.
8. Implementar retrieval híbrido full-text + vector mediante una estrategia documentada, como Reciprocal Rank Fusion.
9. Implementar consultas RAG asíncronas con respuesta estructurada `answer` + `evidence_ids`; validar que todas las citas pertenecen al contexto recuperado.

### Phase 3: Backend API and tests

1. Crear `backend/app/memory_api.py` y registrarlo en `backend/app/main.py`.
2. Separar correctamente respuestas `404`, vacío, indexando, parcial, proveedor no disponible, consulta inválida y error recuperable.
3. Añadir tests de contratos, normalización, chunking, hashes, dimensión, RRF, filtros, deduplicación e idempotencia.
4. Añadir tests de worker para leases stale, reintentos, cambio de hash, transcript no definitivo, proveedor ausente y salida LLM inválida.
5. Añadir integración contra PostgreSQL/pgvector para migración, extensión, índices, upsert, retrieval filtrado, grafo, inspector y citas.
6. Añadir regresión explícita que demuestre que un transcript parcial no crea chunks ni conocimiento.

### Phase 4: Frontend and navigation

1. Crear `frontend/src/features/brain/` con `BrainPage`, `brainApi`, `brainTypes`, `KnowledgeGraphExplorer`, `MemoryQueryConsole`, `NodeInspector`, `EvidenceList`, `DecisionTimeline` y `MemoryStatus`.
2. Ampliar el routing manual de `frontend/src/App.tsx` para `/brain` y activar `Brain & Memoria`.
3. Cargar overview, grafo, timeline e inspector de forma independiente con estados reales.
4. Implementar consulta, filtros removibles, quick prompts, `Ctrl+Enter`, `Meta+Enter` y polling controlado.
5. Implementar grafo accesible con zoom, pan, layouts Semántico/Evolutivo/Por sesión, filtros ontológicos, nodos seleccionables y aristas por tipo.
6. Implementar inspector con identidad, estado, centralidad, relaciones, evidencias, hashes y metadata.
7. Dejar fuera de la interfaz las acciones sin endpoint: editar, exportar, reindexar y auditar prompt.
8. Reutilizar `playFromTimestamp` y añadir deep links de reunión con timestamp y segmento.
9. Construir respuesta RAG, citas, timeline, métricas y restricciones con datos de API, nunca placeholders.
10. Añadir estilos responsive, foco visible, reduced motion, estados no basados solo en color y ausencia de overflow horizontal.

### Phase 5: QA and delivery

1. Añadir `frontend/tests/e2e/brain.spec.ts` para loading, empty, indexing, partial, error, ready, consulta, filtros, grafo, inspector, teclado y navegación a evidencia.
2. Añadir viewport móvil en `frontend/playwright.config.ts` y validar que no hay scroll horizontal.
3. Revisar visualmente 1440px y 390px contra el HTML de diseño, usando datos sintéticos y estados honestos.
4. Ejecutar validaciones focalizadas después de cada slice y luego las suites completas.
5. Entregar handoff independiente a QA/Security sobre definitive-only, procedencia, privacidad, límites, prompts, workers y migraciones.
6. Completar este registro con los archivos reales, comandos, riesgos y estado final cuando la implementación termine.

## Files and ownership

- `docs/features/brain-memoria-global.md`: brief, plan y registro durable de la feature.
- `docs/adr/`: decisión de embeddings, dimensión e infraestructura vectorial.
- `backend/app/memory_contracts.py`: contratos REST y dominio de memoria.
- `backend/app/models.py`: modelos SQLAlchemy derivados de memoria.
- `backend/migrations/versions/`: migración pgvector, tablas e índices.
- `backend/app/embeddings.py`: proveedor local BGE-M3.
- `backend/app/memory_jobs.py`: idempotencia y encolado de indexación/consulta.
- `backend/app/memory_worker.py`: procesamiento durable de jobs.
- `backend/app/memory_api.py`: endpoints globales de memoria.
- `backend/app/audio.py`: límite de persistencia de transcript definitivo y encolado inicial.
- `backend/app/brain.py`, `backend/app/brain_jobs.py`, `backend/app/worker.py`: contratos y patrones existentes a reutilizar.
- `backend/app/config.py`, `backend/pyproject.toml`, `docker/compose.dev.yml`, `docker/compose.nvidia.yml`: configuración y operación.
- `frontend/src/App.tsx`: routing, shell, audio refs y reproducción de evidencia existentes.
- `frontend/src/features/brain/`: página y componentes de la nueva experiencia.
- `frontend/src/styles.css`: lenguaje visual y responsive existente.
- `frontend/tests/e2e/brain.spec.ts`: cobertura E2E.

## Implementation record

Architecture/Data, Intelligence, Backend and Frontend slices complete. Contracts, derived persistence models, portable migrations, embedding configuration, definitive-only indexing, lazy local embedding integration, hybrid literal/vector retrieval, graph projection validation, citation validation, durable memory jobs, Redis Stream workers, the REST API and the read-only `/brain` workflow are implemented. Query workers generate embeddings when BGE-M3 is available, retain literal retrieval as an explicit provider-unavailable fallback, and fence all terminal/requeue mutations by lease. The ORM and migration store PostgreSQL embeddings as `vector(1024)` with an HNSW cosine index. Local validation is complete; live PostgreSQL/pgvector, Redis and model-provider execution remain release gates.

### Frontend slice implementation record

- Objective: integrate a usable, read-only `/brain` page with the existing AdVera shell and actual memory REST contracts.
- Acceptance criteria: the page loads overview, graph and timeline data independently; represents ready, empty, indexing, partial and error states; submits typed queries with polling and `Ctrl+Enter`/`Meta+Enter`; supports keyboard-accessible graph filtering and node selection; shows cited evidence links with timestamp and segment parameters; and remains usable without horizontal overflow on mobile.
- Context and contracts: consumed `GET /api/memory/overview`, `GET /api/memory/graph`, `GET /api/memory/entities/{entity_id}`, `GET /api/memory/timeline`, `POST /api/memory/query` and `GET /api/memory/query/{query_id}` from `backend/app/memory_contracts.py` and `backend/app/memory_api.py`. No transcript or job endpoints were added to the UI.
- Files changed: `frontend/src/features/brain/brainTypes.ts`, `frontend/src/features/brain/brainApi.ts`, `frontend/src/features/brain/BrainPage.tsx`, `frontend/src/App.tsx`, `frontend/src/styles.css` and `frontend/tests/e2e/brain.spec.ts`.
- Decisions and assumptions: the graph uses deterministic dependency-free SVG/CSS positioning; graph controls are read-only; unsupported audio playback is explicitly communicated instead of faking playback; meeting navigation remains manual history routing; optional query arrays are tolerated while queued responses are incomplete.
- Validation: `npm run build` passes; focused Playwright suite passes (`6 passed`) with route mocks for ready, indexing/empty graph, query completion/failure, graph selection, keyboard query, accessibility names and mobile overflow.
- Risks: Playwright emits benign Vite websocket proxy `ECONNABORTED` messages while mocked pages close. Timeline evidence now carries segment and timestamp deep links. The graph endpoint supports speaker, language, date and state filters; the current graph controls still expose only text and node-type filtering, so wiring the advanced controls into the browser remains a follow-up.
- Next action: run the PostgreSQL/pgvector and Redis integration gates, then obtain release approval after independent QA/Security review.

### Backend slice implementation record

### Frontend QA repair slice implementation record

- Objective: close Brain evidence navigation, accessibility, ontology-filter, timeline-action and mobile QA findings without introducing a new router or moving intelligence into the browser.
- Acceptance criteria: evidence opens `/meetings/{meeting_id}?at={seconds}&segment={segment_id}`; manual routing preserves query intent, highlights the definitive segment and invokes existing playback after audio metrics/transcript are ready; missing audio is explicit; timeline evidence is actionable; graph relationships have readable text; all backend-supported filters are usable; focused synthetic E2E coverage passes.
- Context and contracts: consumed the existing meeting `audio-metrics` and definitive `transcript` endpoints plus `MemoryQueryRequest` filters `node_types`, `language`, `speaker`, `start_date`, `end_date` and `state`. No new backend endpoint or transcript contract was added.
- Files changed: `frontend/src/App.tsx`, `frontend/src/features/brain/brainTypes.ts`, `frontend/src/features/brain/BrainPage.tsx`, `frontend/src/styles.css` and `frontend/tests/e2e/brain.spec.ts`.
- Decisions and assumptions: manual `window.history` routing remains in place; playback continues through `playFromTimestamp`; graph relationship text is rendered from the same filtered API edges as the SVG; timeline links open the evidence meeting because the timeline contract exposes evidence IDs but not segment timestamps; per-meeting audio metrics reset before loading to avoid stale availability.
- Validation: `npm run build` passes; `npm run test:e2e -- tests/e2e/brain.spec.ts` passes (`6 passed`). Playwright reports benign Vite websocket `ECONNABORTED` teardown messages while mocked pages close.
- Risks: timeline evidence cannot deep-link to a segment until the timeline API exposes evidence timestamp details; the full frontend E2E suite and independent QA/Security review remain outside this focused repair.
- Next action: hand the repaired slice to QA/Security for independent review, then consider extending the timeline contract if segment-level navigation is required there.

- Objective: provide an end-to-end, definitive-only memory indexing and query backend without coupling failures to Brain or transcript persistence.
- Acceptance criteria: repeated indexing requests for one definitive transcript hash reuse one job; partial transcripts are rejected without chunks; full-text chunks survive unavailable embeddings; graph/API output preserves evidence IDs; queries expose queued, empty, failed and completed-compatible states without invented facts.
- Files changed: `backend/app/memory_jobs.py`, `backend/app/memory_worker.py`, `backend/app/memory_api.py`, `backend/app/audio.py`, `backend/app/main.py`, `backend/app/models.py`, `backend/migrations/versions/0004_memory_job_leases.py`, `backend/migrations/versions/0005_memory_query_filters.py`, `backend/migrations/versions/0006_memory_evidence_links.py`, and `backend/tests/test_memory_backend.py`.
- Decisions: memory jobs remain separate from Brain jobs; transcript hash and provider/model settings define idempotency; embedding failure preserves deterministic full-text chunks and marks the overview partial; graph projection remains strict and stores explicit node/relationship evidence links; an unavailable LLM fails a query with a sanitized provider error rather than generating a response.
- Validation: focused backend memory, contract and intelligence tests pass (`17 passed` for the final memory/model set); touched memory modules pass Ruff and Python compilation. The full backend suite previously passed (`85 passed`); live PostgreSQL/pgvector and Redis worker execution remain unverified locally.
- Risks: SQLite intentionally uses the portable JSON fallback and cannot validate vector operators or HNSW execution. Actual BGE-M3 and Ollama runtime behavior remains unverified; existing unrelated Ruff findings remain in the pre-existing `audio.py` websocket implementation.
- Next action: run Alembic and integration tests against PostgreSQL 16 + pgvector, then perform release review of API exposure, worker recovery and evidence navigation.

### Intelligence slice implementation record

- Objective: provide deterministic, definitive-only indexing and evidence-safe intelligence primitives for a later worker or API orchestration layer.
- Acceptance criteria: provisional transcripts cannot produce chunks or graph data; chunks preserve source provenance and stable hashes; BGE-M3 configuration is exactly 1024 dimensions and unavailable dependencies fail with sanitized errors; retrieval supports literal/vector RRF, filters and deterministic deduplication; graph candidates and answer citations reject invalid provenance.
- Scope: `backend/app/memory_indexing.py`, `backend/app/embeddings.py`, `backend/app/memory_retrieval.py`, `backend/app/memory_graph.py`, `backend/app/memory_citations.py` and synthetic unit tests in `backend/tests/test_memory_intelligence.py`.
- Decisions: one chunk contains consecutive source segments and never splits a segment to manufacture timestamps; BGE-M3 is loaded lazily through the optional sentence-transformers dependency; retrieval uses reciprocal-rank fusion with `1 / (rrf_k + rank)` per modality; Brain occurrences remain separate nodes and only directly evidenced `assigned_to` relationships are projected; no chain-of-thought is stored.
- Validation: focused intelligence, Brain, memory contract and model tests pass (`15 passed`); Python compilation passes. Ruff passes for the new service modules, with unrelated pre-existing findings remaining elsewhere in the backend.
- Risks: the current adapter does not perform model downloads or persistence orchestration; vector dimension/operator behavior and PostgreSQL indexes still require the planned integration environment.
- Next action: hand off these pure services to Backend for durable indexing/query jobs and to QA/Security for independent provenance and provider-failure review.

### QA repair slice implementation record

- Objective: close the critical backend findings in query synthesis, Brain ordering, provenance persistence, retrieval filters and durable memory-job recovery.
- Acceptance criteria: configured Ollama synthesis completes only with structured, context-valid citations; unavailable providers return a sanitized explicit failure; memory indexing remains queued until Brain extraction exists; every chunk segment has usable evidence; all declared filters and `max_results` are enforced; stale jobs are re-enqueued and completion is lease-fenced.
- Context and contracts: definitive transcript data remains the only retrieval source. Query synthesis uses the existing JSON Ollama transport and `validate_answer_citations`; no reasoning or chain-of-thought is persisted.
- Files changed: `backend/app/memory_worker.py`, `backend/app/memory_retrieval.py`, `backend/app/memory_contracts.py`, `backend/app/memory_api.py`, `backend/app/memory_jobs.py`, `backend/app/models.py`, `backend/migrations/versions/0007_memory_provenance_leases.py` and `backend/tests/test_memory_backend.py`.
- Decisions and assumptions: missing Brain extraction requeues without consuming an attempt; chunk provenance stores all source segment IDs and creates one evidence row per segment; query records carry a lease token; date filtering uses the meeting creation date and node filters use evidence-backed projected entities.
- Validation: focused memory/Brain suite passes (`25 passed`); Ruff passes for every touched backend file; Python compilation passes for backend app, tests and migrations.
- Risks and remaining blockers: PostgreSQL/pgvector migration execution, live Redis stream recovery, actual BGE-M3/Ollama execution and independent QA/Security approval remain unverified. The test environment uses SQLite and mocked Ollama transport; SQLite intentionally falls back to JSON for unit tests.
- Next action: execute the live infrastructure gates and retain the feature in this partial release state until they pass.

Initial handoff:

- Objective: build the global, cited, read-only memory workflow.
- Acceptance check: a query about a decision returns cited evidence that opens the correct meeting, segment and audio timestamp, or an explicit insufficient-evidence state.
- Context: existing Brain is meeting-scoped and definitive-only; global graph, embeddings and hybrid retrieval do not exist yet.
- Recommended sequence: Product Owner record -> Architecture/Data contracts and migration -> Intelligence indexing/retrieval -> Backend API/worker -> Frontend route/page -> QA/Security review.
- Critical boundary: no derived memory may consume provisional transcript data.

## Validation

Planned commands and gates:

1. `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests/test_memory*.py backend/tests/test_brain.py backend/tests/test_brain_worker.py -q`
2. PostgreSQL + pgvector integration suite with `alembic upgrade head` against a clean database.
3. `PYTHONPATH=backend .venv/Scripts/python.exe -m ruff check backend/app backend/tests`
4. `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests/test_memory_models.py backend/tests/test_memory_vector_migration.py -q`
5. From `frontend`, `npm run build`
5. From `frontend`, `npx playwright test tests/e2e/brain.spec.ts`, then `npm run test:e2e`
6. `docker compose -f docker/compose.dev.yml -f docker/compose.nvidia.yml config --quiet`
7. Manual keyboard, focus, reduced-motion, mobile overflow, evidence playback and unavailable-provider checks.
8. Independent QA/Security review before marking the feature complete.

Validation completed: backend full suite `85 passed`; final focused memory/model suite `17 passed`; `npm run build` passed; focused Brain E2E `6 passed`; touched memory modules passed Ruff and Python compilation; Alembic head is `0008_pgvector_memory_embeddings`. The full frontend suite is not green because four pre-existing Settings E2E tests expect a legacy metrics GET flow and contain an ambiguous meeting-name locator; those failures are outside this feature slice. PostgreSQL/pgvector, Redis, real embedding/LLM providers and live worker recovery remain pending.

## Risks and open questions

- BGE-M3 may require substantial VRAM, disk cache or CPU time. The worker needs explicit resource limits and observable indexing states.
- Cross-meeting decision reconciliation can create false positives. Occurrence-level decisions and evidence-backed relationships reduce this risk.
- SQLite cannot validate vector operators or HNSW indexes. CI needs a PostgreSQL/pgvector integration environment.
- Brain may finish after transcript persistence. The page must support partial indexing and later graph completion.
- Query context and response payloads need strict limits to avoid memory pressure and accidental sensitive-data exposure.
- Authentication and authorization are intentionally deferred and must be revisited before exposing this view beyond the local single-user deployment.

## Next action

Next action: run clean PostgreSQL 16 + pgvector migration/retrieval checks, Redis duplicate/stale lease recovery, and real BGE-M3/Ollama smoke tests; then complete the independent QA/Security release handoff. The implementation remains local-validation-complete but not release-approved until those gates pass.

### Meeting reprocess implementation record

- Objective: allow an old meeting with a definitive transcript to rebuild Brain and the global memory projection without modifying its original audio or transcript.
- Contract: `POST /api/meetings/{meeting_id}/reprocess` creates a forced Brain job. The endpoint remains blocked when no definitive transcript exists.
- Sequencing: the Brain worker creates/resets the memory index job only after the new extraction is committed, links it through `source_brain_job_id`, and enqueues memory afterwards. Memory rejects an extraction belonging to an older Brain job.
- Frontend: the existing `Reprocesar` action is enabled on an opened meeting and reports that Brain and Memoria will be rebuilt from the definitive transcript.
- Validation: Brain-to-memory regression and blocked endpoint tests pass (`7 passed`); frontend build, Ruff and Python compilation pass.
- Risk: live Redis delivery and real provider execution remain release gates; the operation is intentionally asynchronous and does not guarantee immediate UI completion.

## Memory search: playback from references and remembered search

- Each source of the summary links to `/meetings/{id}?at=<s>&segment=<id>&play=1`; `play=1` makes the meeting start playing every track at the cited second (without it a deep link only positions the audio).
- The last search (question, filters, summary and sources) is stored in the browser (`localStorage`, key `advera.memory.search`, validated on read). Coming back with the browser's back button, or reloading, shows the search pre-filled with the summary and the references, so other references can be opened. A run still in progress is followed again after restoring.

## Memory search: fragments found without an answer (2026-09-30)

- When a search ends with "No hay evidencia suficiente" but did retrieve fragments, "Fragmentos encontrados" now uses the same structure as "Fuentes": a link to the meeting at that second (with `play=1`), the speaker and language, and the quote. The query result keeps, per retrieved chunk, its `content`, `language` and first `segment_id` (`memory_worker._brief`). Runs saved before this change have none of them, so their fragments still list as plain lines.
