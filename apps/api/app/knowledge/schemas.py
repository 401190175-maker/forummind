"""DTOs for server-owned knowledge search scopes and hits."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SearchScope(BaseModel):
    """The complete authorization scope for one knowledge search."""

    model_config = ConfigDict(extra="forbid")

    group_chat_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    allowed_document_ids: list[str] = Field(default_factory=list)

    @field_validator("group_chat_id", "task_id", "data_space")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("scope text must be non-empty")
        return value

    @field_validator("allowed_document_ids")
    @classmethod
    def _validate_document_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("allowed_document_ids must contain non-empty strings")
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_document_ids must be unique")
        return normalized


class SearchHit(BaseModel):
    """A located, indexed document chunk returned to an Agent."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    page_or_location: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    score: float
    source_ref: str = Field(min_length=1)
    source_type: Literal["user_uploaded"] = "user_uploaded"
    data_space: str = Field(min_length=1)
    verification_status: Literal["pending", "verified", "fixture", "unavailable"] = "pending"
    source_mode: Literal["live", "fixture", "replay"] = "live"

    @model_validator(mode="after")
    def _enforce_provenance(self) -> "SearchHit":
        if self.source_mode in {"fixture", "replay"}:
            if self.data_space != "synthetic" or self.verification_status != "fixture":
                raise ValueError("fixture provenance must remain synthetic and fixture-verified")
        elif self.data_space == "synthetic" or self.verification_status == "fixture":
            raise ValueError("live provenance cannot use synthetic or fixture status")
        return self
