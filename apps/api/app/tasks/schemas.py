"""Data-transfer models for research tasks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ResearchTaskStatus = Literal["ready", "running", "awaiting_review", "completed", "failed", "cancelled"]


class DatasetVersionRef(BaseModel):
    """Immutable reference to one persisted experiment dataset version."""

    dataset_id: str = Field(min_length=1)
    version: int = Field(ge=1)

    @field_validator("dataset_id")
    @classmethod
    def _trim_dataset_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("dataset_id must be non-empty")
        return value


class ResearchTask(BaseModel):
    task_id: str = Field(min_length=1)
    group_chat_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=10_000)
    source_clarification_id: str | None = Field(default=None, min_length=1)
    document_ids: list[str] = Field(default_factory=list)
    dataset_refs: list[DatasetVersionRef] = Field(default_factory=list)
    data_space: str = Field(min_length=1)
    status: ResearchTaskStatus
    created_at: float
    updated_at: float

    @field_validator("title", "question", "data_space")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must be non-empty")
        return value

    @field_validator("document_ids")
    @classmethod
    def _unique_document_ids(cls, value: list[str]) -> list[str]:
        if any(not document_id.strip() for document_id in value):
            raise ValueError("document_ids must contain non-empty strings")
        if len(set(value)) != len(value):
            raise ValueError("document_ids must be unique")
        return value

    @field_validator("dataset_refs")
    @classmethod
    def _unique_dataset_refs(cls, value: list[DatasetVersionRef]) -> list[DatasetVersionRef]:
        keys = [(item.dataset_id, item.version) for item in value]
        if len(set(keys)) != len(keys):
            raise ValueError("dataset_refs must be unique")
        return value


class ResearchTaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=10_000)
    document_ids: list[str] = Field(default_factory=list)
    dataset_refs: list[DatasetVersionRef] = Field(default_factory=list)
    data_space: str | None = None

    @field_validator("title", "question")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must be non-empty")
        return value
