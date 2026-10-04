# Gestor de reuniones self-hosted con IA

Nombre AdVera

> Documento maestro de producto, arquitectura y plan de desarrollo. Está pensado para que futuras IAs o desarrolladores puedan continuar el proyecto sin depender de conversaciones anteriores.
>
> **Stack:** Python + React/TypeScript.  
> **Despliegue:** self-hosted server con GPU.  
> **Principio fundamental:** el transcript es la fuente de verdad.

## Estado de este documento

> **Actualizado: 2026-09-30.** Este documento es el baseline de producto y el plan. Las secciones de arquitectura técnica (§4, §5, §9, §17, §19, §20, §36) se han reescrito para describir **lo que está implementado**, ya que divergían del código. Cuando una sección describe un estado actual, es normativa y debe seguir al código. Cuando describe una aspiración (§15, §26 fases futuras, §29), es una meta.
>
> El detalle de implementación y las decisiones con frontera arquitectónica **no viven aquí**: están en [docs/meeting-processing-flow.md](meeting-processing-flow.md) (flujo canónico), [docs/adr/README.md](adr/README.md) (decisiones duraderas) y [docs/features/README.md](features/README.md) (memoria de producto). Si este documento y un ADR discrepan, el ADR manda.

## 1. Visión

Construir un gestor de reuniones AI-first que capture reuniones, las transcriba, identifique hablantes, genere conocimiento estructurado y permita consultar todo el histórico mediante lenguaje natural.

```text
Reunión
  -> Audio original
       +-> Live pipeline -> transcript provisional -> React
       +-> Finalization pipeline -> transcript definitivo
                                      +-> Intelligence pipeline -> conocimiento
                                      +-> embeddings -> búsqueda semántica
  -> Pregunta -> recuperación -> LLM -> respuesta + fuentes
```

El sistema tiene tres etapas explícitas:

1. **Live pipeline:** prioriza baja latencia y visibilidad inmediata durante la reunión.
2. **Finalization pipeline:** reprocesa el audio completo para producir el transcript definitivo.
3. **Intelligence pipeline:** analiza únicamente el transcript definitivo para construir el summary y sus embeddings.

El transcript provisional y el definitivo pertenecen a la misma cadena de procesamiento; no son dos transcripts independientes. El audio original es el origen común y el transcript definitivo es la fuente de verdad persistente.

El objetivo no es únicamente "grabar y resumir", sino crear un **Brain consultable y verificable de las reuniones**.

## 2. Objetivos funcionales

### Reuniones
- Crear, editar, listar, archivar y consultar reuniones.
- Iniciar/detener grabación.
- Importar audio/video.
- Asociar participantes.
- Reproducir audio.

### Audio
- Capturar micrófono.
- Capturar audio del sistema cuando la plataforma lo permita.
- Streaming al servidor.
- Persistencia del original.
- Recuperación ante desconexiones.

### Transcripción
- WhisperX desde el inicio.
- Español (`es`), catalán (`ca`) e inglés (`en`) como mínimo.
- Detección de idioma.
- Reuniones multilingües.
- Segment timestamps.
- Word-level timestamps cuando exista alineamiento adecuado.
- Diarización.
- Reprocesamiento con otros modelos/configuraciones.

### Summary
Extraer:
- resumen;
- decisiones;
- tareas;
- responsables;
- fechas;
- temas;
- hechos;
- preguntas abiertas;
- riesgos;
- ideas;
- memorias;
- relaciones y evolución temporal.

### Consulta
- Full-text search.
- Búsqueda semántica.
- Preguntas sobre una reunión.
- Preguntas sobre múltiples reuniones.
- Preguntas sobre todo el histórico.
- Fuentes navegables hasta transcript y timestamp.

### Privacidad
- Self-hosted.
- Inferencia local por defecto.
- Sin envío a terceros salvo configuración explícita.
- Preparado para proveedores cloud futuros.

---

## 3. Principios arquitectónicos

### 3.1 Transcript = fuente de verdad

El transcript representa el resultado primario de ASR. Durante la reunión puede existir una representación provisional para ofrecer feedback en tiempo real, pero al finalizar el audio debe reprocesarse y consolidarse un transcript definitivo. El LLM nunca sustituye al transcript y el summary nunca se construye sobre segmentos provisionales.

```text
Audio original
  +------------------+
  |                  |
  v                  v
Live ASR          Procesamiento final
  |                  |
  v                  v
Transcript       Transcript definitivo
provisional              |
         +----> Intelligence pipeline
              +-> LLM -> conocimiento
              +-> embeddings
```

Los segmentos provisionales pueden corregirse o sustituirse durante la finalización. Debe conservarse la trazabilidad entre ambos estados para que la UI pueda actualizarse sin crear una segunda fuente de verdad. Si cambia el modelo LLM, el conocimiento puede regenerarse a partir del transcript definitivo. Si cambia el ASR, puede regenerarse desde el audio.

### 3.2 Toda información derivada debe tener procedencia

Una decisión, tarea o memoria debe poder responder:

> ¿De qué reunión y qué segmento procede?

Cadena:

```text
Brain
 -> meeting
 -> transcript segment
 -> timestamp
 -> audio
```

### 3.3 Los embeddings son un índice, no la memoria

No crear una segunda base vectorial en el MVP. Usar **PostgreSQL + pgvector**.

Si se pierden los embeddings, deben poder regenerarse.

### 3.4 No guardar chain-of-thought

No almacenar razonamiento interno del modelo. Sí guardar:
- proveedor;
- modelo;
- versión;
- tarea;
- prompt version;
- referencias de entrada;
- hash de entrada;
- output bruto;
- output parseado;
- estado;
- métricas disponibles.

### 3.5 No acoplar el dominio a WhisperX u Ollama

Crear interfaces de proveedor para ASR, diarización, LLM, embeddings y storage.

---

# 4. Arquitectura

```text
                              React UI
                                  |
                          HTTPS / WebSocket
                                  |
                               FastAPI
                                  |
               +------------------+------------------+
               |                  |                  |
               v                  v                  v
          PostgreSQL            Redis             Storage
          + pgvector             |             audio PCM
               |                  v
               |               Workers
               |        (transcription / summary / brain)
               |                  |
               |      +-----------+-----------+
               |      |           |           |
               |      v           v           v
               |   WhisperX     MOSS        Ollama
               |   (live y      (vLLM,      (LLM y
               |    fallback)  definitive)  embeddings
               |      |           |           |
               |      +-----------+-----------+
               |                  |
               |                  v
               |           Summary / Knowledge
               |                  |
               |                  v
               |          Hybrid Retrieval
               |                  |
               |                  v
               |              LLM Answer
               |                  |
               v                  v
           PostgreSQL        React + Sources
```

MOSS corre como servicio vLLM independiente, no dentro del proceso del backend: en Docker es el servicio `moss-server` (Compose override NVIDIA o ROCm), y en local se publica en el puerto `8001`. El WhisperX del diagrama es a la vez el proveedor live y el fallback explícito cuando MOSS rechaza o no puede procesar una pista.

Si frontend y backend están en la misma máquina:

```text
React -> localhost -> FastAPI -> GPU
```

Si están separados:

```text
React -> HTTPS/WSS -> Server -> GPU
```

La arquitectura es la misma.

---

# 5. Stack

## Frontend

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- WebSocket
- Zod
- Tailwind CSS o sistema de componentes equivalente

El frontend no contiene lógica de IA.

## Backend

- Python
- FastAPI
- Uvicorn
- Pydantic
- SQLAlchemy
- Alembic
- asyncpg

Responsabilidades:
- REST;
- WebSocket;
- auth;
- reuniones;
- audio sessions;
- jobs;
- persistencia;
- orquestación de IA.

No ejecutar inferencia pesada dentro de requests HTTP.

## Database

**PostgreSQL + pgvector**

Una única base para:
- datos de aplicación;
- transcript;
- conocimiento;
- LLM runs;
- embeddings.

## Queue

Redis + workers Python mediante **Redis Streams**. El broker está decidido: no es Celery, RQ ni Dramatiq (ADR 0008). Redis es solo transporte; PostgreSQL conserva estado, intentos, leases, errores y resultados, de modo que un job persistido puede recuperarse y reencolarse.

Workers actuales: transcripción definitiva, Summary, indexación de Brain y consultas de Brain. Detalle en [redis.md](redis.md).

## ASR

La frontera de proveedor está implementada con tres roles configurables e independientes:

| Rol | Variable | Default de despliegue |
|---|---|---|
| Live / provisional | `ASR_LIVE_PROVIDER` | `whisperx` |
| Definitivo | `ASR_DEFINITIVE_PROVIDER` | `moss` |
| Fallback | `ASR_FALLBACK_PROVIDER` | `whisperx` |

WhisperX sirve el live pipeline y actúa como fallback explícito. MOSS (MOSS-Transcribe-Diarize vía vLLM) es el proveedor definitivo: procesa cada pista disponible de forma independiente y es autoritativo para las etiquetas de speaker cuando responde con éxito. MOSS está aceptado solo para desarrollo y canary; el enablement en producción sigue pendiente (ADR 0003, 0007).

El ASR no recibe código de idioma en el flujo normal: los proveedores autodetectan y devuelven el idioma por segmento (ADR 0014). Un operador puede forzar un código ISO 639-1 en una única petición de reproceso, sin persistir preferencia en la reunión.

```text
TranscriptionEngine
  -> WhisperXProvider   (live, fallback)
  -> MossProvider       (definitivo, vía vLLM OpenAI-compatible)
```

Futuro:
- faster-whisper;
- whisper.cpp;
- Parakeet;
- cloud ASR.

## Diarización

Resolución local de speaker embedding (ECAPA-VoxCeleb) más etiquetas por pista, encapsulada como:

```text
DiarizationEngine
  -> LocalDiarizationProvider
```

Las etiquetas de speaker son por pista y no se reconcilian globalmente entre micrófono y sistema; la identidad cruzada de speakers es una decisión posterior (ADR 0003).

## LLM

**Ollama** en local o un servidor compatible con OpenAI (llama.cpp, llama-swap, vLLM), a elegir en Ajustes (ADR 0023), con la configuración `LLM_PROVIDER`, `LLM_MODEL` y `LLM_BASE_URL` compartida entre la API y los workers, de modo que un job encolado reproduce el entorno que lo creó (ADR 0009).

Abstracción:

```text
LLMProvider
  -> OllamaProvider
  -> OpenAIProvider (compatible con OpenAI)
  -> future cloud providers
```

## Embeddings

**BGE-M3, local, exactamente 1024 dimensiones**, con índice HNSW coseno en pgvector. Decidido en ADR 0001 y aplicado en la migración de embeddings.

```text
EmbeddingProvider
  -> local embedding model (BGE-M3)
  -> future cloud provider
```

## Audio storage

Filesystem local, con layout plano por reunión (sin partición por fecha):

```text
<AUDIO_STORAGE_PATH>/<meeting-id>/original.pcm        # pista de micrófono
<AUDIO_STORAGE_PATH>/<meeting-id>/system.pcm          # pista de sistema / media importado
<AUDIO_STORAGE_PATH>/<meeting-id>/transcript.json     # transcript definitivo
<AUDIO_STORAGE_PATH>/<meeting-id>/audio_session.json  # manifiesto de sesión
```

`AUDIO_STORAGE_PATH` es `./data/meetings` en local y `/data/meetings` dentro de los contenedores. Los tracks se guardan como PCM16 mono 16 kHz en reposo; el WAV solo se sintetiza al vuelo para servir HTTP o para enviar a MOSS.

Abstracción:

```text
StorageProvider
  -> LocalFilesystem
  -> S3Compatible (futuro/MinIO)
```

No almacenar audio grande dentro de PostgreSQL.

---

# 6. Streaming de audio

Durante una reunión, la prioridad es el tiempo real: mostrar el transcript mientras se habla, no bloquear la grabación y recuperarse de desconexiones. El análisis profundo queda fuera de este camino crítico.

El audio de reuniones en directo se transportará mediante **WebSocket**.

No hacer un POST por cada fragmento.

```text
React
  |
  | WSS binary frames
  v
FastAPI
  |
  v
AudioSession
```

Formato inicial recomendado:

```text
PCM
16 kHz
mono
16-bit
```

Cada sesión tendrá:
- meeting_id;
- connection_id;
- audio format;
- sequence number;
- bytes recibidos;
- duración;
- estado.

Los frames deben llevar secuencia para detectar pérdidas.

## 6.1 Live pipeline: WhisperX no es ASR streaming puro

Durante el directo no se pasa cada frame directamente a WhisperX.

No pasar cada frame directamente a WhisperX.

Usar:

```text
MICRÓFONO
 -> Audio chunks
 -> VAD
 -> buffer
 -> ventanas de ~5-15 s
 -> overlap
 -> WhisperX rápido
 -> TranscriptStitcher
 -> Transcript provisional/confirmado
 -> PostgreSQL
 -> WebSocket -> React
```

El tamaño de ventana y overlap deben ser configurables y medirse.

El live pipeline debe optimizar baja latencia, consumo razonable de GPU y continuidad de la grabación. Puede producir segmentos `partial` y `confirmed` para la UI. Se pueden añadir detecciones ligeras y opcionales, como cambios de speaker, topic actual, posibles acciones, decisiones o preguntas, pero no se debe ejecutar aquí un análisis LLM completo ni permitir que bloquee la transcripción.

## 6.2 Estados de transcript

```text
partial
confirmed
corrected
```

Los segmentos parciales pueden cambiar. Los confirmados se persisten como resultado provisional estable para la sesión, pero siguen pudiendo ser corregidos por la finalización. `corrected` representa el resultado reemplazado o ajustado durante ese proceso.

El sistema debe conservar la relación entre los segmentos provisionales y los definitivos cuando sea posible. Una corrección no crea una segunda fuente de verdad: actualiza la versión de transcript asociada a la misma reunión y al mismo audio original.

## 6.3 Finalization pipeline

Al terminar la reunión, el audio completo se procesa con prioridad en calidad:

```text
REUNIÓN FINALIZADA
  -> Audio completo
  -> WhisperX
  -> alignment
  -> diarización
  -> Transcript definitivo
```

Este pipeline puede mejorar segmentos, recalcular timestamps, resolver speakers y sustituir el transcript provisional. Debe ejecutarse de forma asíncrona para que finalizar la grabación no dependa de una request HTTP larga.

## 6.4 Intelligence pipeline

El conocimiento solo se genera después de que el transcript definitivo esté disponible:

```text
Transcript definitivo
  -> LLM
  -> Summary / Decisions / Actions / Topics / Memories / Risks
  -> Embeddings
  -> PostgreSQL + pgvector
  -> MEETING READY
```

Este pipeline puede analizar el contexto completo y no debe ralentizar la transcripción en directo. Las entidades derivadas deben referenciar segmentos del transcript definitivo y su `llm_run` correspondiente.

## 6.5 Desconexiones

El WebSocket no es fuente de persistencia.

El servidor debe:
1. almacenar audio;
2. persistir transcript confirmado;
3. mantener estado de reunión;
4. permitir reconexión;
5. recuperar estado;
6. detectar secuencias perdidas.

La reconexión puede restaurar la visualización del transcript provisional y el estado de la sesión. La finalización siempre debe poder reconstruir el resultado desde el audio completo, aunque se hayan perdido eventos WebSocket.

---

# 7. Idiomas

Mínimo:

```text
es = español
ca = catalán
en = inglés
```

No diseñar el modelo para limitarlo a tres idiomas.

Cada segmento debe poder tener su propio idioma:

```text
00:00-10:00 ca
10:00-12:00 es
12:00-12:30 en
```

La detección de idioma en segmentos muy cortos puede ser inestable y debe probarse.

## 7.1 Alineamiento

El soporte de transcripción de catalán no implica automáticamente que cualquier modelo de alineamiento funcione igual de bien.

Implementar:

```text
AlignmentProvider
  -> modelo español
  -> modelo catalán
  -> modelo inglés
  -> fallback
```

Crear tests específicos para catalán, español, inglés y cambios de idioma.

---

# 8. Diarización

Inicialmente los speakers son etiquetas, no personas:

```text
SPEAKER_00
SPEAKER_01
SPEAKER_02
```

Después el usuario puede asociarlos:

```text
SPEAKER_00 -> Ramon
SPEAKER_01 -> Laura
```

Separar siempre `speaker` de `person`.

No implementar reconocimiento biométrico de voz como requisito del MVP.

---

# 9. Modelo de datos

> Fuente de verdad: `backend/app/models.py`. El transcript no vive en PostgreSQL: se persiste como `transcript.json` en el almacenamiento de la reunión, y PostgreSQL guarda los segmentos a los que apuntan los chunks y las evidencias. No existen tablas `recordings`, `people`, `speakers`, `transcript_segments` ni `transcript_words`; el conteo de asistentes y las etiquetas de speaker se derivan del transcript definitivo (ADR 0011, ADR 0005).

## meetings

```text
id                String(36)  PK
title             String(200)
description       Text nullable
started_at        timestamptz nullable
ended_at          timestamptz nullable
duration          Float nullable
status            String(20)   default scheduled
primary_language  JSON         array de idiomas detectados, default []
created_by        String(200) nullable   (sin principal estable todavia)
created_at / updated_at
```

Estados:

```text
scheduled
recording
processing
ready
failed
archived
```

`status` es texto sin constraint en la base de datos; el enum se aplica en Pydantic (`backend/app/meeting_contracts.py`). `primary_language` es un array porque una reunión puede ser multilingüe (ADR 0014). El conteo de asistentes no se almacena: se deriva del transcript definitivo.

## transcription_jobs

```text
id, meeting_id, status, idempotency_key (unique), input_sha256
provider, model, requested_language nullable
attempts, max_attempts, progress
stage            transcribing | finalizing | fallback | completed | retrying | requeued | failed
track, processed_tracks, total_tracks
lease_token nullable, error, created_at, started_at, completed_at, updated_at
```

`stage` es un segundo eje, ortogonal al `status`: describe la fase interna mientras el job sigue en `running`. `requested_language` es el override puntual de reproceso y nunca se escribe en la reunión.

## summary_jobs

```text
id, meeting_id, job_type (EXTRACT_SUMMARY), status
idempotency_key (unique), input_sha256
provider, model, prompt_version, language
attempts, max_attempts, lease_token, error
created_at, started_at, completed_at, updated_at
```

La `idempotency_key` combina reunión, hash del transcript, proveedor, modelo y versión de prompt, de modo que reintentar la misma entrada no crea trabajo duplicado.

## llm_runs

```text
id, job_id
provider, model, prompt_version, input_sha256
status, output (JSON parsed), error
started_at, completed_at
```

Guardar el resultado permite reprocesarlo o depurar parsers. No se almacena chain-of-thought. La tabla `llm_prompts` descrita en el diseño original no se materializó: la versión de prompt vive en el job y en el código.

## summary_extractions

```text
id, meeting_id, job_id, llm_run_id
status, input_sha256, result (JSON), generated_at, created_at
```

**Esto es una desviación deliberada del diseño original.** El plan prevía tablas normalizadas `decisions`, `action_items`, `topics` y `summary_memories`; lo construido guarda la extracción completa como un documento JSON validado por schema en `result`. Consecuencia práctica: no se puede consultar `WHERE status = 'decided'` en SQL sin extraer el JSON, y la memoria temporal con `valid_from`/`valid_until` no está implementada. La normalización queda como trabajo futuro.

## brain_index_jobs

```text
id, meeting_id, source_summary_job_id nullable
status, input_sha256, projection_version
provider, model, model_version
attempts, lease_token, error
created_at, started_at, completed_at, updated_at
```

## brain_chunks

```text
id, meeting_id, index_job_id
segment_id, source_segment_ids (JSON)
content, content_hash, transcript_sha256
start_time, end_time, language, speaker
embedding, embedding_dimension (1024)
embedding_provider, embedding_model, embedding_model_version
created_at
```

**El embedding vive como columna del chunk**, no en una tabla `embeddings` separada. Sigue siendo regenerable: se puede reconstruir desde `content` y `transcript_sha256` sin volver a grabar la reunión.

## Grafo del Brain

```text
brain_entities            node_type, label, normalized_label, status, evidence_ids, source_sha256
brain_relationships       source_entity_id, target_entity_id, relationship_type, confidence, evidence_ids
```

## Grafo de conceptos

```text
brain_concepts                          concept_type, canonical_name, canonical_key (unique), status
brain_concept_aliases                   concept_id, alias, normalized_alias, source_sha256
brain_concept_mentions                  concept_id, meeting_id, mention, confidence, evidence_ids
brain_concept_assignments               concept_id, meeting_id, label, source_type, source_user_id nullable
brain_concept_relationships             source_concept_id, target_concept_id, relationship_type, evidence_ids, source_type
brain_concept_relationship_occurrences  relationship_id, meeting_id, confidence, evidence_ids
```

Los conceptos son **compartidos entre reuniones** y se enlazan a una reunión concreta por mención o por asignación. Las asignaciones manuales del usuario son la fuente de las etiquetas libres de una reunión (ADR 0013); llegan al grafo con `evidence_ids` vacío y no deben interpretarse como evidencia de transcript.

## brain_evidence

```text
id, meeting_id, index_job_id
chunk_id nullable, relationship_id nullable
segment_id, start_time, end_time
transcript_sha256, input_sha256, projection_version
provider, model, model_version
```

Es la tabla que cumple la cadena de procedencia:

```text
Brain -> meeting -> transcript segment -> timestamp -> audio
```

## brain_query_runs

```text
id, query, status, input_sha256
top_k, max_results, filters (JSON), result (JSON)
provider, model, model_version
lease_token, error, created_at, started_at, completed_at
```

Estados: `queued`, `retrieving`, `synthesizing`, `completed`, `empty`, `failed`.

---

# 10. LLM runs

La tabla `llm_runs` se describe en §9 junto al resto del modelo de datos.

Campos: `id`, `job_id`, `provider`, `model`, `prompt_version`, `input_sha256`, `status`, `output`, `error`, `started_at`, `completed_at`.

Guardar el resultado permite reprocesarlo o depurar parsers. No se guarda chain-of-thought, solo salida estructurada validada por schema y su metadata de procedencia.

La tabla `llm_prompts` del diseño original no existe: la versión de prompt se versiona en el código y se referencia desde el job.

---

# 11. Summary

El summary es conocimiento derivado. La extracción se persiste en `summary_extractions.result` como documento JSON estructurado y validado por schema, no como tablas normalizadas.

El documento contiene resumen, temas, decisiones, acciones con responsable y fecha, preguntas abiertas, riesgos, ideas, hechos, memorias y relaciones. Cada elemento apunta a su segmento de origen y al `llm_run` que lo produjo.

El modelo distingue explícitamente conversación, propuesta y decisión, y no convierte una mención en decisión. Los estados de decisión previstos en el diseño original (`proposed`, `decided`, `rejected`, `superseded`, `unknown`) viven **dentro del documento JSON**; no son consultables en SQL.

---

# 12. Memoria temporal

> **No implementado.** Se conserva aquí como meta de producto, no como descripción del sistema.

No se debe borrar automáticamente conocimiento anterior cuando una decisión cambia.

Ejemplo del problema que queda sin resolver:

```text
20/08:
"Se utilizara Kafka"

12/09:
"Finalmente no utilizaremos Kafka"
```

Representación prevista:

```text
Brain A
valid_until = 2026-09-12

Brain B
valid_from = 2026-09-12
```

Lo que sí existe hoy es la relación temporal **a nivel de concepto** mediante el grafo (`brain_concept_relationships` con `relationship_type`), no a nivel de memoria. La contradicción explícita y el `supersedes` siguen siendo trabajo futuro. Conservar siempre las fuentes originales.

---

# 13. Embeddings

**pgvector**, con BGE-M3 local y exactamente 1024 dimensiones, índice HNSW coseno (ADR 0001).

Vectorizado: chunks de transcript, y las entidades, relaciones y conceptos que el worker de Brain proyecta a partir de la extracción de Summary.

Metadatos de cada embedding: modelo, dimensión, versión y el hash de contenido del chunk. El vector se almacena como columna `embedding` de `brain_chunks`, no en una tabla separada.

Los embeddings son regenerables y el sistema no depende exclusivamente de ellos para conservar conocimiento: el contenido vive en `content` y el grafo en las tablas de Brain.

---

# 14. Búsqueda híbrida

No utilizar solamente vector search.

Combinar:

```text
semantic search
+
full-text search
+
structured filters
+
temporal filters
```

Ejemplo:

```text
query = "Kafka"
speaker = Ramon
from = 2026-01-01
topic = Architecture
```

La búsqueda híbrida alimenta al RAG.

---

# 15. Summary Q&A

Flujo:

```text
Pregunta
  |
  v
Query understanding
  |
  +-> filtros
  +-> full text
  +-> embedding
  |
  v
retrieval
  |
  v
context builder
  |
  v
LLM
  |
  v
answer + sources
```

API inicial:

```http
POST /api/summary/query
```

Request:

```json
{
  "query": "¿Qué hemos decidido sobre Kafka?",
  "meeting_ids": [],
  "from": null,
  "to": null
}
```

Response:

```json
{
  "answer": "...",
  "sources": [
    {
      "meeting_id": "m123",
      "segment_id": "s456",
      "start_time": 2052.2,
      "end_time": 2084.1
    }
  ]
}
```

Una respuesta factual sobre reuniones debe tener fuentes navegables.

---

# 16. UI

## Navegación

```text
Inicio
Reuniones
Búsqueda
Summary
Personas
Etiquetas
Ajustes
```

## Pantalla de reunión

Debe mostrar:
- título;
- duración;
- estado;
- transcript;
- speakers;
- idioma;
- timestamps;
- reproductor;
- resumen;
- decisiones;
- acciones;
- búsqueda;
- navegación transcript/audio.

Click en un segmento -> reproducir desde timestamp.

## Pantalla Summary

Entrada principal:

```text
¿Qué quieres saber de tus reuniones?
```

Ejemplos:

```text
¿Qué decidimos sobre Kafka?
¿Qué tareas tengo pendientes?
¿Qué hablamos de Billing esta semana?
¿Cuándo empezamos a hablar de Azure?
¿Qué decisiones han cambiado?
```

Dashboard:
- memorias;
- decisiones;
- tareas;
- temas;
- personas;
- timeline;
- búsqueda semántica;
- fuentes.

---

# 17. Jobs

El diseño original prevía siete tipos de job (`TRANSCRIBE`, `ALIGN`, `DIARIZE`, `ANALYZE_MEETING`, `EMBED_TRANSCRIPT`, `EMBED_SUMMARY`, `REBUILD_INDEX`). **La implementación consolidó los jobs en cuatro tablas**, una por consumidor, sin columna `job_type` salvo en Summary. La descomposición en fases separadas de alineación y diarización no se construyó: ambos pasos ocurren dentro del job de transcripción.

## Tablas de job

| Tabla | Consume | Worker | Stream |
|---|---|---|---|
| `transcription_jobs` | `TranscriptionJob` | Transcription worker | `advera:transcription:jobs` |
| `summary_jobs` | `SummaryJob` (`EXTRACT_SUMMARY`) | Summary worker | `advera:summary:jobs` |
| `brain_index_jobs` | `BrainIndexJob` | Brain worker | `advera:brain:index` |
| `brain_query_runs` | `BrainQueryRun` | Brain worker | `advera:brain:query` |

## Estados

Estados persistidos, comunes a los jobs de proceso:

```text
queued
running
completed
failed
```

`BrainQueryRun` tiene su propio conjunto, porque una consulta pasa por fases de recuperación y síntesis:

```text
queued
retrieving
synthesizing
completed
empty
failed
```

`cancelled` aparece en el enum de eventos WebSocket (`JobStatus`) pero **no es alcanzable**: ningún worker lo escribe y no existe endpoint de cancelación. Está pendiente.

`TranscriptionJob` añade un eje `stage` ortogonal al estado, para exponer la fase interna mientras el job sigue en `running`:

```text
transcribing | finalizing | fallback | retrying | requeued
```

## Campos comunes

```text
id
status
attempts / max_attempts
lease_token            evita que dos consumidores procesen lo mismo
error
created_at / started_at / completed_at / updated_at
```

Los workers reconducen a `queued` los errores recuperables y reencolan el `job_id`; al superar `max_attempts` pasan a `failed`. Un lease antiguo se considera stale y se recupera al reconciliar. Redis es transporte: PostgreSQL es la fuente de verdad del estado y de la recuperación.

Detalle operativo en [redis.md](redis.md).

---

# 18. Pipeline completo

El sistema se divide en tres pipelines con prioridades y responsabilidades diferentes.

## 18.1 Live pipeline: tiempo real

```text
Audio
 -> VAD
 -> buffer 5-15 s
 -> WhisperX rápido
 -> transcript provisional/confirmado
 -> WebSocket -> React
```

Este pipeline no ejecuta análisis LLM completo. La grabación, el almacenamiento del audio y la recuperación ante desconexiones tienen prioridad sobre cualquier enriquecimiento opcional.

## 18.2 Finalization pipeline: calidad

```text
Meeting finished
  -> TranscriptionJob persistido y encolado
  -> Worker asincrono
  -> Tracks PCM completos
  -> MOSS por pista (WhisperX como fallback)
  -> alignment y diarizacion
  -> Transcript definitivo
```

El transcript definitivo reemplaza o corrice el resultado provisional dentro de la misma cadena de transcript. No se mantienen dos transcripts independientes.

La finalización es **asíncrona y durable** (ADR 0008): cerrar la reunión devuelve el control de inmediato y el trabajo continúa en un worker, de modo que una desconexión del cliente o una parada del proceso no dejen la transcripción a medias. El WebSocket nunca espera al proveedor de ASR.

## 18.3 Intelligence pipeline: conocimiento

```text
Transcript definitivo
  -> LLM extraction
  -> Summary / Decisions / Actions / Topics / Memories / Risks
  -> Embeddings
  -> PostgreSQL + pgvector
  -> Summary update
  -> Meeting READY
```

El summary y los embeddings se construyen únicamente a partir del transcript definitivo. Si fallan, pueden reintentarse o regenerarse sin volver a grabar la reunión.

Antes de continuar con la implementación del summary, debe estar estable el live pipeline y la finalización debe producir un transcript definitivo persistente.

---

# 19. Estructura del repositorio

```text
advera/
├── backend/
│   ├── app/                     # módulos planos, sin subdirectorios
│   │   ├── main.py              # registro de routers
│   │   ├── meetings.py          # CRUD, transcript, audio, import, tags
│   │   ├── summary_api.py         # summary + reproceso
│   │   ├── brain_api.py        # grafo, timeline, query
│   │   ├── monitor.py           # Redis Streams, reparación de jobs
│   │   ├── audio.py             # sesión WebSocket, live ASR
│   │   ├── capture_agent.py     # captura de escritorio saliente
│   │   ├── settings.py          # configuración persistente
│   │   ├── system.py            # métricas de host y GPU
│   │   ├── transcription_worker.py
│   │   ├── worker.py            # Summary
│   │   ├── brain_worker.py
│   │   ├── transcription_jobs.py / summary_jobs.py / brain_jobs.py
│   │   ├── moss_asr.py          # proveedor definitivo vía vLLM
│   │   ├── embeddings.py, brain_*.py
│   │   ├── models.py            # SQLAlchemy
│   │   ├── contracts.py, meeting_contracts.py, brain_contracts.py
│   │   └── config.py
│   ├── migrations/versions/     # Alembic
│   ├── tests/
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── features/            # summary, meeting, meetings, monitor, settings
│       ├── App.tsx, main.tsx, styles.css
│       ├── package.json
│       └── Dockerfile
├── agent/                       # agente de captura nativo (Windows)
├── docker/
│   ├── compose.dev.yml
│   ├── compose.nvidia.yml       # override MOSS NVIDIA
│   ├── compose.amd.yml          # override MOSS ROCm
│   └── moss.Dockerfile
├── scripts/                     # dev.ps1, dev.sh, moss_smoke.py
├── docs/
│   ├── adr/                     # índice de decisiones duraderas
│   ├── features/                # memoria de producto
│   ├── design/
│   ├── meeting_manager_project_spec.md
│   ├── meeting-processing-flow.md
│   ├── agent-workflow.md
│   └── redis.md
├── .env.example
└── README.md
```

**El backend no usa el árbol por capas del diseño original** (`api/`, `core/`, `domain/`, `services/`, `workers/`, `db/`). `backend/app/` es un directorio plano de módulos; los prefijos de nombre de archivo (`summary_`, `brain_`, `transcription_`) expresan la frontera. El ownership de las fronteras está en `docs/agent-workflow.md`, no en la forma del árbol.

**No existe `docker/compose.yml`**: hay `compose.dev.yml` más los overrides de GPU.

---

# 20. API

Routers registrados en `backend/app/main.py`. Las rutas del diseño original que nunca se construyeron se marcan; las reales están agrupadas por router.

## Salud

```http
GET    /api/health
```

## Reuniones

```http
GET    /api/meetings
POST   /api/meetings
GET    /api/meetings/{id}
PATCH  /api/meetings/{id}
DELETE /api/meetings/{id}
GET    /api/meetings/{id}/transcript
GET    /api/meetings/{id}/transcription     # estado durable del job de transcripción
GET    /api/meetings/{id}/audio/{track}
GET    /api/meetings/{id}/audio-metrics
POST   /api/meetings/{id}/imports           # import de media externo -> system.pcm
GET    /api/meetings/tags
GET    /api/meetings/{id}/tags
GET    /api/meetings/{id}/tags/suggestions
POST   /api/meetings/{id}/tags
DELETE /api/meetings/{id}/tags/{assignment_id}
```

## Summary

```http
GET    /api/meetings/{id}/summary
POST   /api/meetings/{id}/summary
POST   /api/meetings/{id}/reprocess        # acepta { "language": "ca" } opcional
```

El diseño original preveía `GET /api/meetings/{id}/summary`, `/decisions` y `/actions`. No existen: los datos de Summary se sirven como documento desde `GET /{id}/summary`.

## Brain

```http
GET    /api/brain/overview
GET    /api/brain/graph
GET    /api/brain/concept-graph
GET    /api/brain/entities/{id}
GET    /api/brain/timeline
POST   /api/brain/query
GET    /api/brain/query/{id}
```

El diseño original prevía `POST /api/summary/query`; la ruta real es `POST /api/brain/query`. `GET /api/search` no se construyó como endpoint separado: la búsqueda híbrida se expone a través de `/api/brain/query`.

## Monitor

```http
GET    /api/monitor
POST   /api/monitor/brain-jobs/{id}/repair
```

El diseño original prevía `GET /api/jobs/{id}`; el estado durable de un job concreto se consulta en `GET /api/meetings/{id}/transcription`.

## Capture agent

```http
GET    /api/capture-agent/capabilities
POST   /api/capture-agent/sessions
GET    /api/capture-agent/sessions/current
DELETE /api/capture-agent/sessions/current
```

## Settings y métricas

```http
GET    /api/settings
PUT    /api/settings
POST   /api/settings/ollama/models
GET    /api/system-metrics
```

## WebSocket

```text
WS  /ws/meetings/{meeting_id}/audio
WS  /ws/brain/query/{query_id}
WS  /api/system-metrics/ws
WS  /ws/capture-agents/{agent_id}
WS  /ws/capture-agents/{agent_id}/sessions/{capture_session_id}/tracks/{track}/pcm
WS  /ws/capture-agent/{capture_session_id}/{track}/levels
WS  /ws/capture-agent/{capture_session_id}/{track}/pcm
```

El diseño original prevía `WS /ws/meetings/{id}/events`; no existe. El progreso de transcripción viaja por el socket de audio y el estado durable se consulta por HTTP, no por eventos.

Todos los eventos de progreso son una optimización de entrega. PostgreSQL es la fuente de verdad del estado.

---

# 21. Seguridad

Desde el principio:

- HTTPS recomendado.
- Autenticación.
- Autorización/RBAC preparado.
- Password hashing.
- Secrets por variables de entorno/secret manager.
- Autenticar WebSockets.
- Validar uploads.
- Límites de tamaño/duración.
- Rate limiting.
- No registrar audio ni transcript en logs.
- No registrar contenido sensible innecesario.
- Auditoría de proveedores externos.

---

# 22. Observabilidad

Añadir desde temprano:

- logs estructurados;
- métricas;
- duración de jobs;
- latencia ASR;
- real-time factor;
- latencia LLM;
- profundidad de cola;
- uso GPU;
- VRAM;
- duración total de procesamiento;
- errores.

Métricas:

```text
transcription_latency_seconds
transcription_realtime_factor
llm_latency_seconds
job_queue_depth
gpu_brain_used_bytes
meeting_processing_duration_seconds
```

No registrar contenido sensible por defecto.

---

# 23. GPU

El servidor con GPU es el entorno principal de inferencia.

No asumir que WhisperX y LLM pueden ocupar toda la VRAM simultáneamente.

Crear conceptualmente:

```text
InferenceResourceManager
```

para poder controlar:
- número de workers GPU;
- concurrencia;
- prioridad;
- OOM;
- uso de VRAM.

MVP:

```text
1 ASR worker GPU
1 LLM worker GPU
```

Optimizar después de medir.

---

# 24. Tests

## Unitarios

- Audio framing.
- Sequence handling.
- Transcript stitching.
- Language detection.
- LLM JSON parsing.
- Schema validation.
- Temporal memories.
- Retrieval.
- Permissions.

## Integración

- PostgreSQL.
- pgvector.
- Redis.
- WebSocket.
- Storage.
- WhisperX.
- Ollama.

## E2E

```text
create meeting
 -> stream audio
 -> transcript
 -> finish
 -> summary
 -> query
 -> sources
```

---

# 25. Tests lingüísticos

Crear dataset realista:

```text
Spanish
Catalan
English
Spanish + Catalan
Spanish + English
Catalan + English
Spanish + Catalan + English
```

Medir por idioma:
- WER;
- CER;
- timestamps;
- language detection;
- diarization;
- alignment;
- latencia.

No asumir que una mejora en inglés mejora catalán.

---

# 26. Roadmap de implementación

Estado real a 2026-09-30. Las fases 0 a 10 están construidas; lo que faltaba se lista explícitamente al final.

## Fase 0 — Arquitectura
- [x] Repositorio, contratos, `.env.example`, Docker Compose, CI, linters, tests básicos.

## Fase 1 — Infraestructura
- [x] FastAPI, React, PostgreSQL, pgvector, Redis, Alembic, health checks, logging.

## Fase 2 — Meetings
- [x] CRUD, estados, listado, detalle, archivado.

## Fase 3 — Audio
- [x] Captura, WebSocket, `AudioSession`, frames binarios, sequence numbers, storage, reconexión.
- [x] Captura de escritorio nativa con agente propio y pista de sistema por loopback.
- [x] Import de media externo.

## Fase 4 — WhisperX
- [x] Worker, carga de modelo, VAD, ventanas, stitching, timestamps, persistencia, eventos realtime.

## Fase 5 — Idiomas
- [x] es/ca/en, autodetección por segmento, sin override forzado (ADR 0014).
- [x] Override puntual de idioma en reproceso, sin persistir preferencia.
- [ ] Dataset multilingüe y métricas WER/CER completas por idioma.

## Fase 6 — Diarización
- [x] Resolución local de speakers, etiquetas por pista.
- [ ] Reconciliación de identidad de speaker entre micrófono y sistema.

## Fase 7 — Transcript UI
- [x] Reproductor, click-to-seek, búsqueda, speakers, idioma, progreso de finalización.

## Fase 8 — Summary
- [x] `LLMProvider`, Ollama, prompts versionados, structured output, `llm_runs`, extracción con procedencia.
- [ ] Normalizar la extracción en tablas consultables (`decisions`, `action_items`, `topics`, `summary_memories`).

## Fase 9 — Embeddings
- [x] `EmbeddingProvider`, BGE-M3 1024 dims, pgvector, chunks, índices, búsqueda híbrida en base de datos.

## Fase 10 — Summary Q&A
- [x] Retrieval, context builder, LLM, respuestas con fuentes y timestamps.

## Fase 11 — Robustez
- [x] Observabilidad, métricas de host y GPU, monitor de colas, límites.
- [ ] **Autenticación y RBAC.** Es el bloqueo principal: sin principal estable, `created_by` y el actor de las etiquetas son nullable y no hay multiusuario posible.
- [ ] **Backups y restore probados.** El diseño está escrito; no se ha ejecutado un restore real.
- [ ] **Cancelación de jobs.** `cancelled` existe en el enum de eventos pero es inalcanzable.
- [ ] Rate limiting y endurecimiento de uploads.

## Fase 12 — Evolución
- [ ] Memoria temporal con contradicciones y `supersedes` (§12).
- [ ] Artefactos de traducción con su fuente y hash (ADR 0014).
- [ ] Calendario, videoconferencias, multiusuario, proyectos, cloud inference.
- [ ] Chunking de MOSS para grabaciones por encima del límite de desarrollo de 2 horas.
- [ ] Validación de hardware AMD.

---

# 27. Backups

Respaldar:

```text
PostgreSQL
Audio storage
Configuración no secreta
```

Los embeddings son regenerables.

Restauración:

```text
PostgreSQL
+
Audio
  |
  v
rebuild embeddings
```

Probar periódicamente un restore real.

---

# 28. Reprocesamiento

Debe existir:

```text
Reprocess meeting
```

con posibilidad de cambiar:
- ASR;
- idioma;
- alignment;
- diarización;
- LLM;
- prompt.

El audio original permanece intacto.

El sistema debe mantener una noción de versión de transcript/procesamiento.

---

# 29. Futuras integraciones

## Calendario
- Google Calendar.
- Microsoft 365.
- CalDAV.

## Videoconferencia
- Teams.
- Google Meet.
- Zoom.
- Webex.

Cada integración debe estudiarse por separado. No asumir que todas permiten captura de audio de la misma forma.

## Cloud inference

Configuración futura:

```text
ASR: local
LLM: cloud
Embeddings: local
```

o:

```text
ASR: local
LLM: local
Embeddings: local
```

La UI debe mostrar claramente qué datos salen del servidor.

---

# 30. Reglas para futuras IAs

Antes de modificar código:

1. Leer README.
2. Leer documentación de arquitectura.
3. Leer modelo de datos.
4. Leer documentación del AI pipeline.
5. Revisar migraciones.
6. Revisar tests.
7. Revisar contratos API/WebSocket.
8. Ejecutar tests.
9. Entender el flujo actual.
10. Proponer cambios arquitectónicos antes de introducir nueva infraestructura.

Después de modificar:

1. Implementar.
2. Añadir tests.
3. Ejecutar tests.
4. Revisar migraciones.
5. Revisar Docker.
6. Actualizar documentación.
7. Revisar seguridad.
8. Comprobar que no se rompieron contratos.

## No introducir tecnología sin justificarla

Antes de añadir una nueva DB, vector DB, broker, framework o proveedor:

```text
¿Por qué la arquitectura actual no basta?
¿Qué problema concreto resuelve?
¿Qué coste operacional añade?
¿Puede esconderse tras una interfaz?
¿Qué datos migra?
¿Cómo se revierte?
```

Evitar complejidad distribuida prematura.

# 30.1 Agentes de IA para controlar el desarrollo y la producción

Los agentes de IA deben organizarse por responsabilidades. No se debe crear un único agente con acceso ilimitado a todo el repositorio, la base de datos y la infraestructura.

Los agentes pueden proponer cambios, escribir código, ejecutar tests y preparar despliegues. Las operaciones destructivas o irreversibles requieren aprobación humana explícita.

## Agente orquestador

Responsabilidades:
- recibir objetivos y convertirlos en tareas verificables;
- seleccionar el agente especializado adecuado;
- mantener el estado del roadmap y las dependencias;
- coordinar contratos entre frontend, backend, workers y base de datos;
- verificar la Definition of Done;
- impedir que el summary se construya sobre transcript provisional;
- generar un informe final con cambios, tests, riesgos y decisiones pendientes.

No debe modificar directamente producción ni saltarse los gates de calidad.

## Agentes de desarrollo

### Agente de arquitectura y contratos

Responsable de:
- mantener la arquitectura y las interfaces de proveedores;
- revisar decisiones técnicas;
- controlar compatibilidad de API, WebSocket y eventos;
- detectar acoplamientos indebidos a WhisperX, Ollama o Redis;
- actualizar documentación técnica.

### Agente backend y dominio

Responsable de:
- implementar FastAPI, servicios y reglas de negocio;
- reuniones, grabaciones, transcript, summary y búsqueda;
- validación Pydantic;
- autorización y manejo de errores;
- tests unitarios e integración.

### Agente frontend

Responsable de:
- React, TypeScript y navegación;
- estado de reuniones y jobs;
- WebSocket y reconexión;
- transcript en tiempo real;
- reproducción sincronizada con timestamps;
- visualización de fuentes, errores y estados de procesamiento.

### Agente de audio y live pipeline

Responsable de:
- captura y normalización de audio;
- framing y sequence numbers;
- VAD, buffers y ventanas de 5-15 segundos;
- AudioSession y almacenamiento original;
- WhisperX rápido;
- latencia, pérdida de frames y recuperación de desconexiones.

### Agente de finalización y calidad lingüística

Responsable de:
- reprocesamiento del audio completo;
- alignment y diarización;
- stitching y versionado de transcript;
- soporte es/ca/en;
- evaluación WER, CER, timestamps y speakers;
- promoción de transcript provisional a definitivo.

### Agente de inteligencia y recuperación

Responsable de:
- prompts versionados y schemas de salida;
- Ollama y otros `LLMProvider`;
- summary, decisiones, acciones, topics, memorias y riesgos;
- procedencia de cada entidad derivada;
- embeddings, búsqueda híbrida, RAG y Summary Q&A;
- validación de respuestas y fuentes.

Este agente solo puede consumir transcript definitivo.

### Agente de datos y migraciones

Responsable de:
- modelos SQLAlchemy y migraciones Alembic;
- índices PostgreSQL y pgvector;
- integridad referencial;
- migraciones reversibles;
- seeds y datos de prueba;
- compatibilidad durante despliegues graduales.

Las migraciones de producción requieren revisión humana.

### Agente de QA y release

Responsable de:
- tests unitarios, integración y E2E;
- pruebas de contratos REST/WebSocket;
- pruebas de regresión del transcript;
- pruebas multilingües;
- pruebas de carga y reconexión;
- generación de release notes;
- bloqueo de releases con fallos críticos.

## Agentes de operación

### Agente DevOps y despliegue

Responsable de:
- Docker Compose, CI/CD e imágenes;
- configuración por entorno;
- health checks y rollback;
- gestión de workers;
- validación de secretos y variables de entorno;
- despliegues a staging y producción.

No debe desplegar directamente cambios no aprobados.

### Agente SRE, observabilidad y GPU

Responsable de:
- logs estructurados sin contenido sensible;
- métricas de ASR, LLM, jobs y WebSocket;
- colas, latencia, real-time factor y errores;
- uso de GPU y VRAM;
- OOM y saturación de workers;
- alertas y diagnóstico de incidentes;
- backups, restore y capacidad de almacenamiento.

### Agente de seguridad y privacidad

Responsable de:
- autenticación, autorización y WebSocket;
- validación de uploads;
- rate limiting;
- detección de secretos;
- revisión de dependencias;
- auditoría de proveedores externos;
- comprobación de que audio, transcript y prompts no se filtran a logs.

Debe revisar cualquier cambio que exponga datos fuera del servidor.

## Flujo de control entre agentes

```text
Solicitud
  -> Orquestador
  -> Agente especializado
  -> Tests y validación
  -> QA y revisión de seguridad
  -> Staging
  -> Aprobación humana
  -> Producción
  -> Observabilidad y rollback
```

Reglas obligatorias:

1. Un agente no puede aprobar su propio cambio crítico.
2. Ningún agente puede borrar audio, transcript definitivo o conocimiento sin una operación explícita y auditable.
3. Las migraciones, cambios de autenticación, cambios de proveedores y despliegues requieren revisión humana.
4. Todo agente debe declarar archivos modificados, comandos ejecutados, tests y riesgos conocidos.
5. Las credenciales de producción nunca se incluyen en prompts ni se almacenan en el repositorio.
6. Las acciones de producción deben ser idempotentes y disponer de rollback cuando sea posible.

---

# 31. Definition of Done

Una tarea está terminada cuando:

```text
[x] Código
[x] Tests
[x] Error handling
[x] Logging apropiado
[x] Documentación
[x] Migración si aplica
[x] API contract actualizado
[x] Docker actualizado si aplica
[x] Seguridad revisada
[x] Sin secretos en código
```

---

# 32. Primer milestone técnico

Demostrar:

```text
React
  |
  | WebSocket
  v
FastAPI
  |
  v
AudioSession
  |
  v
Audio Storage
  |
  v
Job
  |
  v
WhisperX
  |
  v
PostgreSQL
  |
  v
React Transcript
```

Con audio real en:
- español;
- catalán;
- inglés.

Medir:
- calidad;
- timestamps;
- persistencia;
- reconexión;
- GPU;
- latencia.

No avanzar al summary hasta que este flujo sea estable.

---

# 33. Segundo milestone

Demostrar:

```text
Meeting
 -> Transcript
 -> Ollama
 -> Structured Analysis
 -> Summary
 -> Decisions
 -> Actions
 -> Memories
 -> PostgreSQL
```

Todo conocimiento debe tener fuente.

---

# 34. Tercer milestone

Demostrar:

```text
Histórico de reuniones
 -> PostgreSQL + pgvector
 -> pregunta
 -> hybrid retrieval
 -> LLM
 -> respuesta
 -> fuentes
 -> transcript
 -> audio
```

---

# 35. Criterio final de éxito

El proyecto no se considera completo cuando simplemente transcribe y resume.

Debe proporcionar una cadena verificable:

```text
Respuesta
   |
   v
Conocimiento
   |
   v
Fuente
   |
   v
Transcript
   |
   v
Timestamp
   |
   v
Audio original
```

La característica diferencial del producto es que las reuniones se convierten en un **Brain consultable, temporal, trazable y verificable**.

---

# 36. Decisiones arquitectónicas definitivas

| Área | Decisión |
|---|---|
| Producto | Gestor de reuniones AI-first |
| Despliegue | Self-hosted server |
| Localhost | Sí, misma arquitectura |
| Frontend | React + TypeScript |
| Backend | Python + FastAPI |
| ASR live | WhisperX |
| ASR definitivo | MOSS (MOSS-Transcribe-Diarize vía vLLM OpenAI-compatible) |
| ASR fallback | WhisperX |
| Límite de idioma ASR | Ninguno en transcripción normal; autodetección por segmento |
| Idiomas mínimos | Español, catalán, inglés |
| Diarización | Resolución local de speaker embedding, etiquetas por pista |
| LLM inicial | Ollama, configuración compartida con los workers |
| LLM abstraction | Sí |
| Database | PostgreSQL |
| Vector search | pgvector, BGE-M3 1024 dims, HNSW coseno |
| Segunda vector DB | No en MVP |
| Queue | Redis Streams + workers Python; PostgreSQL es la fuente de verdad del estado |
| Audio transport | WebSocket |
| Audio inicial | PCM 16 kHz mono 16-bit |
| Audio storage | Filesystem, layout plano por reunión |
| Object storage futuro | MinIO/S3 compatible |
| Transcript storage | `transcript.json` atómico en el almacenamiento de la reunión |
| Fuente de verdad | Transcript definitivo |
| Original | Audio |
| Finalización | Asíncrona, en worker, durable |
| Summary | Documento JSON estructurado en `summary_extractions.result` |
| Embeddings | Columna `embedding` de `brain_chunks`, índice regenerable |
| Grafo | Entidades y relaciones más grafo de conceptos compartido entre reuniones |
| Chain-of-thought | No se almacena |
| LLM outputs | Raw + parsed, con versión de prompt y hash de entrada |
| Procedencia | Obligatoria, vía `brain_evidence` |
| Cloud AI | Futuro, opcional |
| Auth | **Pendiente.** La API no tiene principal |
| Desktop app | No es requisito del MVP |
