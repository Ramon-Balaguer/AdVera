"""Settings API (spec §20; settings-ollama-url.md, ollama-connectivity-model-selection.md)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from app import runtime_settings
from app.config import Settings, get_settings
from app.llm import LLMError, list_models
from app.net_safety import UnsafeDestination, assert_safe_destination
from app.runtime_settings import RuntimeSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])

AppSettings = Annotated[Settings, Depends(get_settings)]


class SettingsResponse(BaseModel):
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_output_language: str
    llm_configured: bool
    setup_completed: bool
    setup_required: bool


class ModelDiscoveryRequest(BaseModel):
    provider: Literal["ollama", "openai"] = "ollama"
    base_url: str


class ModelDiscoveryResponse(BaseModel):
    base_url: str
    models: list[str]


def _response(runtime: RuntimeSettings) -> SettingsResponse:
    return SettingsResponse(
        **runtime.model_dump(),
        llm_configured=runtime.llm_configured,
        setup_required=runtime.setup_required,
    )


@router.get("", response_model=SettingsResponse)
async def get_runtime_settings(settings: AppSettings) -> SettingsResponse:
    return _response(runtime_settings.load(settings))


class SettingsUpdate(BaseModel):
    llm_provider: Literal["ollama", "openai"] | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_output_language: Literal["en", "es", "ca"] | None = None
    setup_completed: bool | None = None


@router.put("", response_model=SettingsResponse)
async def put_runtime_settings(body: SettingsUpdate, settings: AppSettings) -> SettingsResponse:
    current = runtime_settings.load(settings)
    changes = body.model_dump(exclude_none=True)
    try:
        updated = RuntimeSettings.model_validate(current.model_dump() | changes)
    except ValidationError:
        # An invalid value never overwrites the valid persisted settings.
        raise HTTPException(status_code=422, detail="INVALID_SETTINGS") from None
    if "llm_base_url" in changes:
        try:
            await assert_safe_destination(updated.llm_base_url)
        except UnsafeDestination as error:
            raise HTTPException(status_code=422, detail=error.code) from None
    runtime_settings.save(settings, updated)
    return _response(updated)


@router.post("/models", response_model=ModelDiscoveryResponse)
async def discover_models(body: ModelDiscoveryRequest) -> ModelDiscoveryResponse:
    try:
        base_url = RuntimeSettings(llm_base_url=body.base_url).llm_base_url
    except ValidationError:
        raise HTTPException(status_code=422, detail="INVALID_URL") from None
    try:
        await assert_safe_destination(base_url)
    except UnsafeDestination as error:
        raise HTTPException(status_code=422, detail=error.code) from None
    try:
        models = await list_models(body.provider, base_url)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=error.code) from None
    return ModelDiscoveryResponse(base_url=base_url, models=models)
