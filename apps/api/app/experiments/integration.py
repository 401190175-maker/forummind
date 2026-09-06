"""Task-scoped experiment analysis entry point for governed consumers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.experiments.analysis import AnalysisService
from app.experiments.schemas import AnalysisResult, AnalysisSpec


class DatasetScope(BaseModel):
    """Server-owned dataset scope carried alongside a runtime invocation."""

    model_config = ConfigDict(extra="forbid")

    group_chat_id: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    dataset_ids: list[str] = Field(min_length=1)

    @field_validator("group_chat_id", "data_space")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("dataset scope text must be non-empty")
        return value

    @field_validator("dataset_ids")
    @classmethod
    def _unique_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("dataset_ids must contain unique non-empty strings")
        return normalized


class ScopedExperimentAnalysis:
    """Run only whitelisted analysis against an explicitly allowed dataset."""

    def __init__(self, analysis: AnalysisService) -> None:
        self.analysis = analysis

    def analyze(
        self,
        scope: DatasetScope,
        dataset_id: str,
        spec: AnalysisSpec,
        *,
        version: int | None = None,
    ) -> AnalysisResult:
        if dataset_id not in scope.dataset_ids:
            raise ValueError("dataset scope denied")
        try:
            result = self.analysis.analyze_dataset(
                dataset_id,
                spec,
                version=version,
                group_chat_id=scope.group_chat_id,
            )
        except KeyError as exc:
            # Do not reveal whether a dataset exists outside the caller's scope.
            raise ValueError("dataset group scope denied") from exc
        if result.data_space != scope.data_space:
            raise ValueError("dataset data space mismatch")
        return result
