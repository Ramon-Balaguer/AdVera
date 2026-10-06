# Meeting Processing Flow

This is the canonical end-to-end flow for a recorded AdVera meeting. Keep it synchronized with the capture, transcript, ASR, Summary, Brain, provenance and deployment contracts.

```mermaid
flowchart TD
    A[User starts meeting] --> B[Capture audio]
    B --> C1[Microphone PCM16 mono 16 kHz]
    B --> C2[System audio PCM16 mono 16 kHz]
    C1 --> D[Backend audio ingress]
    C2 --> D
    D -. Control, levels and metrics .-> UI[Frontend]
    D --> E[Persist original tracks]
    D --> F[Live ASR provisional transcript]
    F --> G[Show Live transcript]
    G -. Presentation only, never an intelligence input .-> Y

    E --> H{Meeting stopped}
    H --> I[State: processing]
    I --> J[Create TranscriptionJob in PostgreSQL]
    J --> JQ[Redis Stream: advera:transcription:jobs]
    JQ --> JW[Transcription worker]
    JW --> K[Read complete stored tracks]

    K --> K1[Send microphone track to definitive provider]
    K --> K2[Send system track to definitive provider]
    K1 --> L1{Provider succeeds}
    K2 --> L2{Provider succeeds}
    L1 -->|MOSS| M1[Normalize timestamps speakers language]
    L1 -->|Failure| F1[Fallback provider, if configured]
    L2 -->|MOSS| M2[Normalize timestamps speakers language]
    L2 -->|Failure| F2[Fallback provider, if configured]
    F1 --> T1[Definitive microphone segments]
    F2 --> T2[Definitive system segments]
    M1 --> T1
    M2 --> T2

    T1 --> U[Merge segments by timestamp and retain track provenance]
    T2 --> U
    U --> V[Resolve language metadata]
    V --> W{Valid definitive segments}
    W -->|No| X[State: failed; preserve audio and prior transcript]
    W -->|Yes| Y[Atomically save transcript.json]

    Y --> Z[Definitive transcript: source of truth]
    Z --> BA[Create or force Summary job with shared LLM config (Ollama or OpenAI-compatible)]
    BA --> BB[Summary worker]
    BB --> BC[Extract summary, topics, decisions, actions, questions and risks]
    BB --> BD[Extract concepts and relationships with evidence]
    BC --> BE[Persist structured Summary result]
    BD --> BF[Project Brain: facts, concepts and global graph]

    Z --> BG[Create Brain index job]
    BG --> BH[Create transcript chunks]
    BH --> BI[Generate BGE-M3 embeddings]
    BI --> BJ[Persist PostgreSQL and pgvector]
    BF --> BJ
    BJ --> BK[Update hybrid search and graph views]
    BK --> BL[Meeting processing complete]
    BL --> BM[Knowledge available to later meetings]

    BD -. Generated after this transcript .-> BM

    MI[User imports audio or video] --> MV[Validate multipart media]
    MV --> MX[Extract mono PCM16 16 kHz with ffmpeg]
    MX --> MS[Persist as system.pcm; delete the uploaded file; no microphone required]
    MS --> J
```

## Processing order

1. Store the original microphone and system tracks, or import one media file and store only its extracted audio as `system.pcm`; the uploaded file is deleted (ADR 0016). The desktop Capture Agent sends each track on its own PCM socket straight to the backend audio session; the browser microphone over the meeting WebSocket is the fallback (ADR 0010).
2. Emit Live transcription only as provisional user feedback; ASR receives no language override and detects language metadata on segments.
3. When capture stops, persist a `TranscriptionJob`, commit it and enqueue its ID in Redis.
4. The transcription worker reads the complete stored audio.
5. Send each available track independently to MOSS for definitive transcription.
6. Use the configured fallback provider, if any, when MOSS fails.
7. Normalize segments, speakers, timestamps, track identity and detected original language; never translate the definitive transcript. Speaker labels come from the provider when it supplies them (ADR 0003); otherwise local ECAPA diarization labels each track, numbering speakers uniquely within the meeting (ADR 0017). Diarization failure never fails the transcript.
8. Save the definitive transcript atomically before scheduling Summary.
9. Snapshot the shared `LLM_PROVIDER`, `LLM_MODEL` and `LLM_BASE_URL` configuration when scheduling Summary.
10. Run Summary only from the persisted definitive transcript.
11. Generate evidence-backed concepts, relationships, decisions, actions and summaries.
12. Build Brain chunks and BGE-M3 embeddings in PostgreSQL/pgvector. The index job is created right after the definitive transcript commits, next to the Summary job; it does not wait for Summary because chunks and embeddings come from the transcript alone. The concept and relationship projection (BD → BF) is a separate index job (`kind = concepts`) that Summary creates when its extraction completes (ADR 0019); because it only exists after Summary, it never waits for it and chunk indexing never waits for it. The text stages read more than the transcript: Summary and its concept projection read the transcript, the meeting's notes (with their @references expanded) and the names given to its speakers; Brain chunks read the transcript and the notes. Their jobs are keyed by that input (`backend/app/analysis_input.py`), which equals `segments_sha256` when there are no notes or names. Saving notes or names queues the text stages again, never the audio; a job made for older input fails as `INPUT_CHANGED` (ADR 0020, ADR 0021).
13. Expose searchable knowledge and the graph with provenance to the original meeting.
14. Make concepts generated from this meeting available as historical context for later meetings only.
15. Imported media skips microphone capture and enters the same definitive queue with one available system track.

After definitive transcription, persist the distinct non-null segment languages as the meeting's `primary_language` array. The original-language definitive transcript is the source of truth: future language lists and translations must be separate derived artifacts carrying source and target language, provider/model and source transcript hash. ASR receives no language override during normal transcription; an operator may force one language on a single reprocess request without persisting a meeting preference.

## MOSS runtime selection

MOSS is served through the OpenAI-compatible vLLM boundary. Select the GPU runtime explicitly: NVIDIA uses `vllm/vllm-openai` with the NVIDIA Compose override, while AMD uses `vllm/vllm-openai-rocm` with the ROCm device mappings. Do not mix CUDA and ROCm overrides; if MOSS is unavailable, the configured fallback provider, if any, remains explicit.

For local development, `docker/compose.dev.yml` configures `VLLM_MAX_AUDIO_CLIP_FILESIZE_MB=200` and `VLLM_MAX_AUDIO_DECODE_DURATION_S=7200` (two hours). These limits control uploaded file size and decoded duration independently from `MOSS_MAX_MODEL_LEN=65536` and `MOSS_MAX_NEW_TOKENS=65536`. Increasing them does not guarantee sufficient context or GPU brain; recordings beyond the tested capacity must be chunked before MOSS processing. The values are overrideable through `.env` and should be capacity-tested before production use.

## Reprocessing

`Reprocesar` reads the stored original tracks again, reruns definitive ASR, replaces `transcript.json` only after valid output, and then force-schedules Summary. If retranscription fails, the prior transcript remains intact and Summary is not rescheduled.

## Failure boundaries

- Capture failure: preserve any stored audio and expose an explicit failed state.
- Definitive ASR failure: retain audio; use the fallback provider when configured.
- Empty or invalid definitive result: do not publish a successful transcript.
- Summary or Brain failure: keep the definitive transcript intact and expose a recoverable derived-job state.
- Summary jobs created by the transcription worker use the same provider, model and endpoint defaults as the API and Summary worker. A job persisted without a provider stays failed until it is explicitly retried or regenerated; the transcription worker refuses to guess one.
- MOSS unavailable: the service remains operational through the explicit fallback provider, when one is configured.

## Maintenance rule

When a change modifies a processing stage, provider, contract, state, provenance rule, queue, persistence boundary or deployment path, update this document in the same change and link the relevant ADR and feature record.
