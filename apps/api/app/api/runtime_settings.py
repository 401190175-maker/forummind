"""Local Runtime settings API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent_runtime.config import RuntimeConfigStatus, runtime_config


class RuntimeSettingsRequest(BaseModel):
    provider: str = Field(min_length=1)
    base_url: str = ""
    model: str = Field(min_length=1)
    api_key: str = ""


router = APIRouter(prefix="/runtime-settings", tags=["runtime-settings"])


@router.get("", response_model=RuntimeConfigStatus)
def get_runtime_settings() -> RuntimeConfigStatus:
    return runtime_config.status()


@router.put("", response_model=RuntimeConfigStatus)
def put_runtime_settings(body: RuntimeSettingsRequest) -> RuntimeConfigStatus:
    try:
        return runtime_config.configure(
            provider=body.provider,
            base_url=body.base_url,
            model=body.model,
            api_key=body.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("", response_model=RuntimeConfigStatus)
def delete_runtime_settings() -> RuntimeConfigStatus:
    return runtime_config.clear()
