"""Runtime configuration shared by the API and workers.

Names and defaults follow docs/redis.md and docs/meeting_manager_project_spec.md §5.
ASR defaults follow ADR 0007: MOSS is opt-in, so every role defaults to WhisperX.
No ASR language setting exists: providers autodetect (ADR 0014).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://advera:advera@localhost:5432/advera"
    redis_url: str = "redis://localhost:6379/0"
    audio_storage_path: str = "./data/meetings"

    transcription_queue_name: str = "advera:transcription:jobs"
    brain_queue_name: str = "advera:brain:jobs"
    memory_index_queue_name: str = "advera:memory:index"
    memory_query_queue_name: str = "advera:memory:query"

    asr_live_provider: str = "whisperx"
    asr_definitive_provider: str = "faster-whisper"
    asr_fallback_provider: str = "whisperx"
    # separate-live-definitive-asr-models.md: tiny for live, small for definitive.
    asr_live_model: str = "tiny"
    asr_definitive_model: str = "small"
    # nvidia-cuda-asr-runtime.md: CPU/int8 by default; CUDA/float16 through the NVIDIA override.
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"

    # Local diarization (spec §5, local-speaker-diarization.md): ECAPA-VoxCeleb embeddings.
    # "none" disables it; transcripts then carry no speaker labels.
    diarization_provider: str = "local"
    diarization_model: str = "speechbrain/spkrec-ecapa-voxceleb"
    diarization_cache_dir: str = "./data/models"
    diarization_threshold: float = 0.5
    diarization_min_speakers: int | None = None
    diarization_max_speakers: int | None = None

    # Optional bearer token the Capture Agent must present (outbound-capture-agent-websocket.md).
    capture_agent_token: str | None = None

    transcription_max_attempts: int = 3
    transcription_lease_seconds: int = 600
    transcription_heartbeat_seconds: int = 30
    transcription_reconcile_seconds: int = 30

    # meeting-media-import.md: 5 GiB default upload limit; conversion uses ffmpeg (ADR 0012).
    media_import_max_bytes: int = 5 * 1024**3
    media_import_timeout_seconds: int = 3600
    ffmpeg_binary: str = "ffmpeg"


@lru_cache
def get_settings() -> Settings:
    return Settings()
