"""Persistent runtime settings (persistent-runtime-settings.md, ADR 0009).

Operator choices that change without a redeploy (LLM endpoint, model and output language)
live in one local JSON file shared by the API and the workers. Environment variables supply
the defaults; the file overrides them. The file holds no secrets and no meeting content.
An invalid update never overwrites the valid persisted file.
"""

import json
import os
import tempfile
import urllib.parse
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import Settings


class RuntimeSettings(BaseModel):
    llm_provider: Literal["ollama", "openai"] = "ollama"
    llm_base_url: str = Field(max_length=500)
    llm_model: str = Field(default="", max_length=200)
    # ADR 0009: textual Summary fields are written in this language; the transcript is not.
    llm_output_language: Literal["en", "es", "ca"] = "en"
    # Set when the first-start wizard is finished or skipped (ADR 0025): it never comes back.
    setup_completed: bool = False

    @field_validator("llm_base_url")
    @classmethod
    def _url(cls, value: str) -> str:
        value = value.strip()
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("llm_base_url must be an http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("llm_base_url must not contain credentials")
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
        )

    @field_validator("llm_model")
    @classmethod
    def _model(cls, value: str) -> str:
        return value.strip()

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_model)

    @property
    def setup_required(self) -> bool:
        """The first-start wizard is shown until a model is chosen or the wizard is closed."""
        return not self.setup_completed and not self.llm_configured


def defaults(settings: Settings) -> RuntimeSettings:
    return RuntimeSettings(
        llm_provider=settings.llm_provider,
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        llm_output_language=settings.llm_output_language,
    )


def load(settings: Settings) -> RuntimeSettings:
    """Defaults from the environment, overridden by the persisted file when it is valid."""
    base = defaults(settings)
    path = Path(settings.runtime_settings_path)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeSettings.model_validate(base.model_dump() | dict(stored))
    except (OSError, ValueError, TypeError, ValidationError):
        return base


def save(settings: Settings, runtime: RuntimeSettings) -> None:
    path = Path(settings.runtime_settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(runtime.model_dump(), handle, indent=2)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
