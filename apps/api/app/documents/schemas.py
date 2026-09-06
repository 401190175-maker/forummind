"""Data-transfer models for uploaded research documents."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DocumentStatus = Literal["uploaded", "processing", "ready", "failed"]
IndexJobStatus = Literal["uploaded", "processing", "ready", "failed"]


class DocumentRecord(BaseModel):
    document_id: str = Field(min_length=1)
    group_chat_id: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    storage_key: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    status: DocumentStatus
    created_at: float
    updated_at: float


class DocumentIndexJob(BaseModel):
    document_id: str = Field(min_length=1)
    status: IndexJobStatus
    error_code: str = ""
    retry_count: int = Field(ge=0)
    started_at: float | None = None
    finished_at: float | None = None
    updated_at: float
