# Plan de desarrollo: Gestor de reuniones AI-first

TL;DR: proyecto greenfield por incrementos verticales. Primero se definen los agentes, permisos y flujo de trabajo; después se fijan contratos y se levanta la infraestructura; luego se estabiliza el flujo de audio/live transcript y la finalización; solo entonces se construyen inteligencia, embeddings y Brain Q&A. Cada etapa tiene tests y un gate de aceptación antes de desbloquear la siguiente.

> **Actualizado: 2026-09-30.** Las fases 0 a 10 están construidas; la 11 está parcial. Este documento conserva el plan y su razonamiento de secuenciación, pero las decisiones ya resueltas se marcan como tales y las rutas que se indican son las reales. El estado actual por feature está en [docs/features/README.md](features/README.md) y el flujo canónico en [meeting-processing-flow.md](meeting-processing-flow.md).

## 1. Descubrimiento y decisiones iniciales

1. Confirmar hardware GPU, VRAM disponible, sistema operativo objetivo y si desarrollo/producción usarán Docker. **Parcialmente resuelto:** la selección de runtime está decidida (ADR 0007, NVIDIA vía `vllm/vllm-openai`, AMD vía `vllm/vllm-openai-rocm`); el dimensionado y la certificación de hardware de producción siguen pendientes.
2. Elegir broker de jobs entre Celery, RQ o Dramatiq. **Resuelto:** ninguno de los tres. Se usa Redis Streams como transporte con jobs persistidos en PostgreSQL, y leases para impedir el doble procesamiento (ADR 0008).
3. Elegir modelo de embeddings local y dimensión del vector. **Resuelto:** BGE-M3 local con exactamente 1024 dimensiones, vector(1024) e índice HNSW coseno en pgvector (ADR 0001).
4. Definir autenticación inicial, estrategia de secretos y política de usuarios; dejar RBAC preparado aunque el MVP pueda ser single-user. **Pendiente.** Es hoy el bloqueo principal: sin principal estable, `created_by` y el actor de las etiquetas son nullable.
5. Definir formato de eventos WebSocket, política de edición/versionado del transcript y límites de audio.
6. Documentar estas decisiones en ADRs breves antes de crear infraestructura adicional.

## Fase previa: agentes y flujo de trabajo

Debe completarse antes del bootstrap y bloquea la implementación paralela.

1. Definir el agente orquestador y los agentes especializados: arquitectura/contratos, backend, frontend, audio/live pipeline, finalización lingüística, inteligencia/recuperación, datos/migraciones, QA/release, DevOps, SRE/GPU y seguridad/privacidad.
2. Para cada agente, documentar responsabilidad, entradas, salidas, archivos autorizados, herramientas permitidas, límites de acceso y criterios de finalización.
3. Definir el flujo de trabajo: solicitud -> orquestador -> agente especializado -> implementación -> tests -> QA/seguridad -> staging -> aprobación humana -> producción -> observabilidad/rollback.
4. Definir handoffs y contratos entre agentes: issue/tarea, contexto, archivos tocados, decisiones, tests ejecutados, riesgos y siguiente acción.
5. Crear gates obligatorios: ningún agente aprueba su propio cambio crítico; migraciones, auth, proveedores, datos sensibles y producción requieren revisión humana.
6. Definir permisos separados para desarrollo, staging y producción; ningún agente recibe acceso ilimitado ni credenciales de producción en prompts.
7. Crear plantillas de tareas, ADRs, informes de release, incidentes y rollback.
8. Alinear el trabajo de agentes con los milestones: audio/live antes del brain, transcript definitivo antes de inteligencia y retrieval antes de Brain Q&A.

Archivos principales: `docs/agent-workflow.md`, `docs/adr/`, plantillas de issues/PR, reglas de CI y configuración de permisos.

Verificación: una tarea de ejemplo atraviesa el flujo completo; los handoffs contienen contexto y evidencia; un cambio crítico se bloquea sin aprobación humana; CI rechaza contratos, tests o seguridad incompletos.

## 2. Fase 0: bootstrap y contratos

Bloquea todas las fases posteriores.

1. Crear `backend/`, `frontend/`, `docker/`, `scripts/` y configuración raíz.
2. Crear `README.md`, `.gitignore`, `.env.example` y CI.
3. Configurar Python, FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, ruff y mypy si se adopta tipado estricto.
4. Configurar React, TypeScript, Vite, Router, TanStack Query, Zod y lint/format.
5. Definir contratos de dominio: reuniones, grabaciones, jobs, transcript, speakers, knowledge y fuentes.
6. Definir contratos REST y WebSocket, incluyendo `AudioFrame`, `TranscriptPartial`, `TranscriptConfirmed`, `AudioSessionState` y eventos de job.
7. Definir interfaces `JobQueue`, `StorageProvider`, `TranscriptionEngine`, `AlignmentProvider`, `DiarizationEngine`, `LLMProvider` y `EmbeddingProvider`.
8. Añadir tests de schemas, serialización y compatibilidad de contratos.

Archivos principales: `README.md`, `.env.example`, `backend/pyproject.toml`, `frontend/package.json`, configuración CI y módulos de contratos.

Verificación: backend y frontend arrancan en modo desarrollo; tests de contratos pasan; CI ejecuta lint, typecheck y tests básicos.

## 3. Fase 1: infraestructura local

Depende de Fase 0.

1. Crear Docker Compose de desarrollo y producción para FastAPI, frontend, PostgreSQL + pgvector y Redis.
2. Implementar configuración por entorno, health checks, logging estructurado y correlation/request IDs.
3. Implementar Alembic y la primera migración para extensiones y tablas base.
4. Implementar worker mínimo y `JobQueue` detrás de la interfaz elegida.
5. Añadir límites de request, uploads y timeouts sin registrar audio ni transcript.
6. Preparar volúmenes para PostgreSQL, Redis y `/data/meetings`.

Archivos principales: `docker/compose.dev.yml`, `docker/compose.nvidia.yml`, `docker/compose.amd.yml`, `backend/app/config.py`, `backend/app/models.py`, `backend/migrations/versions/`, Dockerfiles.

Verificación: `docker compose up`; health checks de API, PostgreSQL/pgvector y Redis; migraciones aplican y revierten en un entorno limpio.

## 4. Fase 2: dominio de reuniones y persistencia

Puede avanzar en paralelo entre backend y frontend tras fijar contratos; la integración depende de ambos.

1. Implementar modelos y migraciones para `meetings`, `recordings`, `people`, `speakers`, `transcript_segments`, `transcript_words` y `jobs`.
2. Implementar estados de reunión y transiciones válidas: scheduled, recording, processing, ready, failed, archived.
3. Implementar CRUD de reuniones, archivado, detalle y listado paginado.
4. Implementar metadatos de grabación y `StorageProvider` local.
5. Implementar endpoints de jobs y eventos de progreso.
6. Crear la primera pantalla React de reuniones y detalle básico.

Verificación: tests de dominio, migraciones, permisos iniciales y API; desde React se puede crear, editar, listar, abrir y archivar una reunión.

## 5. Fase 3: audio y Live pipeline

Es el primer camino crítico. Depende de Fases 1-2 y contratos.

1. Capturar micrófono en el navegador y normalizar a PCM 16 kHz, mono, 16-bit.
2. Implementar WebSocket binario autenticado para audio.
3. Implementar `AudioSession`, sequence numbers, ack/heartbeat, detección de huecos y estado de conexión.
4. Persistir audio por chunks de forma independiente del WebSocket y permitir reanudación.
5. Implementar VAD, buffers configurables de 5-15 s, overlap y `TranscriptStitcher`.
6. Integrar WhisperX rápido detrás de `TranscriptionEngine`.
7. Persistir segmentos `partial` y `confirmed`; emitirlos a React sin ejecutar LLM completo.
8. Implementar reconexión, recuperación de estado y cierre idempotente de sesión.
9. Medir latencia end-to-end, real-time factor, pérdida de frames, bytes almacenados y uso de VRAM.

Archivos principales: `backend/app/audio.py` (sesión WebSocket y live ASR), `backend/app/moss_asr.py` (proveedor definitivo), `backend/app/transcription_worker.py`, `backend/app/transcription_jobs.py`, `backend/app/capture_state.py`, `frontend/src/features/meetings/`. Nota: `backend/app/` es plano; los prefijos de archivo expresan la frontera y el árbol por capas del plan original no se construyó.

Verificación: tests de framing, secuencias, reconexión, persistencia, stitching y WebSocket; grabación continua de 10 minutos sin pérdida; transcript visible pocos segundos después de hablar.

## 6. Milestone 1 y gate de estabilidad

No iniciar brain antes de superar este gate.

1. Ejecutar flujo React -> WebSocket -> FastAPI -> AudioSession -> storage -> job -> WhisperX -> PostgreSQL -> React.
2. Probar audio real en español, catalán, inglés y al menos una mezcla de idiomas.
3. Confirmar que una desconexión no pierde audio y que el servidor puede reconstruir desde el audio.
4. Confirmar que segmentos provisionales no se usan como conocimiento.
5. Registrar baseline de latencia, calidad ASR, timestamps, GPU y capacidad.

Gate: live transcript estable, audio persistente, reconexión funcional y pruebas críticas verdes.

## 7. Fase 4: Finalization pipeline y transcript definitivo

Depende del gate del Milestone 1.

1. Crear jobs asíncronos `TRANSCRIBE`, `ALIGN` y `DIARIZE` para audio completo.
2. Procesar el recording original completo con WhisperX de calidad.
3. Implementar `AlignmentProvider` por idioma y fallback.
4. Integrar diarización pyannote y etiquetas `SPEAKER_00`, etc.
5. Definir versión de transcript/procesamiento y relación entre segmentos provisionales y definitivos.
6. Promover el transcript definitivo solo cuando el pipeline completo termine correctamente.
7. Mantener el audio original y permitir reprocesamiento con otros modelos/configuraciones.
8. Añadir dataset y métricas WER, CER, timestamps, detección de idioma y diarización para es/ca/en.

Verificación: una reunión finalizada produce transcript definitivo persistente; errores dejan la reunión en estado recuperable; los segmentos definitivos mantienen procedencia al recording y timestamps.

## 8. Fase 5: UI completa de transcript

Puede empezar con fixtures, pero la aceptación depende del transcript definitivo.

1. Mostrar estados provisional, confirmado, corregido y definitivo sin confundirlos.
2. Implementar reproductor de audio y click-to-seek por segmento.
3. Añadir speakers, idioma, timestamps y word-level timestamps cuando existan.
4. Añadir búsqueda dentro del transcript y filtros.
5. Añadir edición controlada y auditoría/versionado si se permite editar.
6. Mostrar progreso de finalización, errores y acción de reprocesamiento.

Verificación: cualquier segmento navega al timestamp correcto; la UI se actualiza durante live y tras finalización.

## 9. Milestone 2 y gate de transcript

1. Probar una reunión real completa desde grabación hasta transcript definitivo.
2. Verificar que ninguna entidad de brain o embedding se crea antes del transcript definitivo.
3. Verificar fuentes `meeting_id`, `segment_id`, timestamps y recording.
4. Verificar reprocesamiento sin perder el audio original.

Gate: fuente de verdad estable y verificable.

## 10. Fase 6: Intelligence pipeline

Depende del Milestone 2.

1. Implementar `OllamaProvider` y configuración del modelo.
2. Crear prompts versionados y schemas estructurados para summary, decisions, actions, topics, memories y risks.
3. Implementar `llm_runs` con proveedor, modelo, versión, prompt, hash, raw output, parsed output, estado, error y métricas.
4. Validar salidas; reintentar errores transitorios; conservar raw output sin chain-of-thought.
5. Crear entidades derivadas con `source_segment_id`, `source_meeting_id` y `llm_run_id`.
6. Diferenciar conversación, propuesta y decisión; no convertir automáticamente una mención en decisión.
7. Ejecutar este pipeline solo cuando el transcript definitivo esté disponible.

Verificación: una reunión produce resumen, decisiones, acciones, topics y memorias estructuradas; cada elemento tiene procedencia navegable; el fallo de LLM no rompe transcript ni audio.

## 11. Fase 7: embeddings y búsqueda híbrida

Depende de Fase 6 y de la decisión de modelo de embeddings.

1. Implementar `EmbeddingProvider` local.
2. Crear chunks de transcript definitivo y embeddings para decisiones, tareas, memorias y resúmenes.
3. Crear tabla/vector schema con `content_hash`, modelo, dimensiones y entidad.
4. Crear índices pgvector y full-text search.
5. Combinar semantic search, full-text search, filtros estructurados y filtros temporales.
6. Implementar jobs `EMBED_TRANSCRIPT`, `EMBED_BRAIN` y `REBUILD_INDEX`.
7. Permitir regenerar embeddings sin perder conocimiento.

Verificación: queries semánticas y literales recuperan fuentes relevantes; rebuild produce el mismo índice lógico; no se depende solo del vector.

## 12. Fase 8: Brain Q&A

Depende de Fase 7.

1. Implementar `POST /api/brain/query`.
2. Implementar query understanding, filtros, retrieval y context builder con límites de contexto.
3. Generar respuestas mediante `LLMProvider` sin almacenar chain-of-thought.
4. Exigir fuentes en respuestas factuales.
5. Devolver meeting, segment, timestamps y referencias navegables a transcript/audio.
6. Mostrar en React la pregunta, respuesta, filtros, fuentes y estado de confianza.

Verificación: preguntas sobre una reunión, varias reuniones y el histórico devuelven respuestas con fuentes; ausencia de evidencia se expresa como incertidumbre.

## 13. Fase 9: seguridad, operación y producción

Parte debe comenzar en Fases 1-3; hardening completo depende del E2E.

1. Implementar autenticación y autorización; preparar RBAC.
2. Proteger WebSockets, uploads, endpoints de jobs y audio.
3. Añadir límites de tamaño/duración, rate limiting, validación de MIME y checksum.
4. Añadir métricas: ASR latency, real-time factor, LLM latency, queue depth, GPU/VRAM y meeting processing duration.
5. Implementar `InferenceResourceManager`, límites de workers y manejo de OOM.
6. Añadir retries, cancelación, idempotencia y dead-letter/estado de fallo.
7. Configurar backups de PostgreSQL y audio; probar restore real y rebuild de embeddings.
8. Añadir alertas, runbooks, staging, rollback y despliegue controlado.
9. Revisar logs para excluir audio, transcript, prompts sensibles y secretos.

Verificación: restore probado, fallo de proveedor recuperable, despliegue a staging, rollback y alertas operativas verificadas.

## 14. Milestone 3: producto end-to-end

Validar:

`histórico -> PostgreSQL + pgvector -> pregunta -> retrieval híbrido -> LLM -> respuesta -> fuentes -> transcript -> timestamp -> audio`.

Criterios:

- una reunión puede completarse sin perder audio;
- transcript live y definitivo son distinguibles y trazables;
- inteligencia solo usa transcript definitivo;
- conocimiento y respuestas tienen fuentes;
- embeddings pueden regenerarse;
- backups y restore funcionan;
- tests unitarios, integración y E2E pasan.

## 15. Evolución posterior fuera del MVP

No implementar hasta estabilizar el producto principal:

- memoria temporal avanzada, contradicciones y relaciones;
- multiusuario, proyectos y RBAC completo;
- calendario;
- Teams, Meet, Zoom y Webex;
- MinIO/S3;
- cloud inference;
- desktop app;
- reconocimiento biométrico de voz;
- optimizaciones avanzadas de GPU.

## Archivos y áreas principales

Layout real. El árbol por capas del plan original no se construyó; ver la nota en §5.

- Raíz: `README.md`, `.gitignore`, `.env.example`, `.github/workflows/`, `docker/`, `scripts/`, `agent/`.
- Docker: `docker/compose.dev.yml` más los overrides `compose.nvidia.yml` y `compose.amd.yml`, y `moss.Dockerfile`. **No existe `docker/compose.yml`.**
- Backend: `backend/app/` plano (`main.py`, `meetings.py`, `audio.py`, `capture_agent.py`, `brain_api.py`, `memory_api.py`, `monitor.py`, `settings.py`, `system.py`, `*_worker.py`, `*_jobs.py`, `models.py`, `contracts.py`, `config.py`), más `backend/migrations/versions/`, `backend/tests/`, `requirements.txt`, `pyproject.toml`, `Dockerfile`.
- Frontend: `frontend/src/` con `features/{brain,meeting,meetings,monitor,settings}`, `App.tsx`, `main.tsx`, `styles.css`, `package.json`, `Dockerfile`.
- Contratos/datos: schemas REST/WebSocket en `backend/app/contracts.py`, modelos SQLAlchemy en `models.py`, migraciones Alembic, prompts versionados en el código, y ADRs en `docs/adr/`.

## Decisiones y supuestos

- El documento de especificación es la fuente de requisitos de producto; los ADR son la fuente de verdad de las decisiones técnicas con frontera arquitectónica.
- El repositorio parte de cero; no se migrará código existente.
- PostgreSQL + pgvector es la única base de datos del MVP.
- El audio original se conserva fuera de PostgreSQL mediante `StorageProvider`, en un layout plano por reunión.
- El transcript definitivo es la única base válida para brain y embeddings.
- Los agentes de IA pueden asistir desarrollo y operación, pero no tienen acceso ilimitado ni saltan gates; migraciones, seguridad, proveedores y producción requieren revisión humana.
- Integraciones externas y funcionalidades avanzadas quedan fuera del MVP.

## Riesgos residuales y decisiones pendientes

1. **Hardware GPU de producción.** Eligió el runtime (ADR 0007) pero falta dimensionado, canary sobre corpus licenciado y validación del hardware AMD antes de producción.
2. **Auth/RBAC.** Sin principal estable, `created_by` y el actor de las etiquetas son nullable y no hay multiusuario posible. Bloquea el resto de la fase 11.
3. **Cancelación de jobs.** `cancelled` existe en el enum de eventos pero ningún worker lo escribe y no hay endpoint.
4. **Backups y restore.** El diseño está escrito; no se ha ejecutado un restore real.
5. **Edición de transcript.** Decidir si es corrección auditada o nueva versión derivada. Sin resolver.
6. **Normalización del Brain.** La extracción vive en un documento JSON; consultar decisiones o acciones en SQL requiere normalizarlo en tablas.
7. **Memoria temporal.** Sin `valid_from`/`valid_until` por memoria ni `supersedes` explícito (§12 del spec).
8. **Artefactos de traducción.** Diferidos por ADR 0014; requieren un contrato nuevo que preserve el transcript original y su hash.

## Verificación global

- Lint, typecheck y tests de backend/frontend en cada PR.
- Tests de contratos REST/WebSocket en cada cambio de API.
- Tests de modelo separados de CI rápida y ejecutados en entorno GPU.
- Milestone 1 antes de inteligencia.
- Milestone 2 antes de embeddings/Q&A.
- Milestone 3 antes de declarar MVP terminado.
