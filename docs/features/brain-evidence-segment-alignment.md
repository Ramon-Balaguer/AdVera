# Feature: Alineación de evidencias en consultas Brain
Status: complete
Last updated: 2026-09-21

## Problem and target user

Las consultas globales pueden generar una respuesta adecuada usando el contenido completo de un chunk, pero mostrar citas de segmentos que no sostienen esa respuesta porque varios `evidence_ids` se enviaban agrupados sin el texto individual de cada segmento.

Target user: persona que verifica una respuesta de Brain contra el transcript definitivo y el audio.

## Product brief

- Desired outcome: cada cita mostrada corresponde al `evidence_id`, segmento, timestamp y texto que respaldan la respuesta.
- Smallest useful increment: incluir en el contexto de Ollama la relación explícita entre cada ID de evidencia y el texto canónico de su segmento.
- In scope: construcción del contexto RAG, prueba de regresión y trazabilidad de la cita persistida.
- Out of scope: cambiar Ollama, embeddings, ASR, contratos REST o UI.
- Acceptance criteria: Ollama recibe IDs con su `segment_id` y `transcript_text`; una respuesta cita el ID del segmento relevante; la API/UI muestran ese mismo segmento y texto; IDs inválidos siguen fallando.
- Failure behavior: si la salida cita un ID desconocido se rechaza; si no hay evidencia suficiente se mantiene `empty`.
- Data/provenance constraints: solo transcript definitivo, sin contenido real en tests ni chain-of-thought.
- Assumptions: la UI renderiza fielmente las citas recibidas por el backend.
- Open question: confirmar en producción que las consultas nuevas dejan de presentar segmentos no relacionados; no bloquea la regresión local.

## Implementation record

### Decisions

- Mantener el contenido agregado del chunk como contexto de recuperación.
- Añadir una lista de segmentos con `evidence_id`, `segment_id`, timestamps y texto definitivo para que la selección del modelo sea verificable.

### Files changed

- `backend/app/memory_worker.py`
- `backend/tests/test_memory_backend.py`
- `docs/features/brain-evidence-segment-alignment.md`

### Validation

- `python -m pytest tests/test_memory_backend.py -k test_query_worker_completes_with_valid_citations_and_rejects_unknown_citations -q`: passed (`1 passed`).
- `python -m pytest tests/test_memory_backend.py -q`: passed (`13 passed`).

### Risks and next action

Riesgo residual: consultas ya persistidas con citas incorrectas no se corrigen retroactivamente; deben volver a ejecutarse. Siguiente acción: handoff a QA/Security para validar consultas reales con Ollama y PostgreSQL/pgvector.
