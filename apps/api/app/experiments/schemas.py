"""Experiment dataset and analysis contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DataOrigin = Literal["live", "fixture", "replay"]
VerificationStatus = Literal["unverified", "verified", "fixture", "unavailable"]
SampleFieldType = Literal["sample_id", "number", "text"]


class DatasetImportMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    group_chat_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    source_mode: DataOrigin
    sample_schema: dict[str, SampleFieldType] = Field(min_length=1)
    units: dict[str, str] = Field(default_factory=dict)
    conditions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("dataset_id", "project_id", "group_chat_id", "source_document_id", "data_space")
    @classmethod
    def _trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("metadata text must be non-empty")
        return value

    @model_validator(mode="after")
    def _enforce_origin(self) -> "DatasetImportMetadata":
        if self.source_mode in {"fixture", "replay"} and self.data_space != "synthetic":
            raise ValueError("fixture and replay datasets must remain synthetic")
        if self.source_mode == "live" and self.data_space == "synthetic":
            raise ValueError("live datasets cannot use synthetic data space")
        return self


class ExperimentDatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    latest_version: int = Field(ge=1)
    filename: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    row_count: int = Field(ge=0)
    columns: list[str] = Field(min_length=1)
    created_at: float
    updated_at: float


class ExperimentPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    columns: list[str] = Field(min_length=1)
    inferred_field_types: dict[str, SampleFieldType]
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    validation_findings: list[dict[str, Any]] = Field(default_factory=list)


class ExperimentRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=2)
    values: dict[str, Any] = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    source_location: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    source_mode: DataOrigin
    verification_status: VerificationStatus

    @model_validator(mode="after")
    def _enforce_origin(self) -> "ExperimentRow":
        if self.source_mode in {"fixture", "replay"}:
            if self.data_space != "synthetic" or self.verification_status != "fixture":
                raise ValueError("fixture provenance must remain synthetic and fixture-verified")
        elif self.data_space == "synthetic" or self.verification_status == "fixture":
            raise ValueError("live provenance cannot use synthetic or fixture status")
        return self


class ExperimentDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    project_id: str = Field(min_length=1)
    group_chat_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    sample_schema: dict[str, SampleFieldType] = Field(min_length=1)
    units: dict[str, str] = Field(default_factory=dict)
    conditions: dict[str, Any] = Field(default_factory=dict)
    rows: list[ExperimentRow] = Field(min_length=1)
    data_space: str = Field(min_length=1)
    source_mode: DataOrigin
    verification_status: VerificationStatus
    created_at: float
    updated_at: float

    @model_validator(mode="after")
    def _enforce_origin(self) -> "ExperimentDataset":
        if self.source_mode in {"fixture", "replay"}:
            if self.data_space != "synthetic" or self.verification_status != "fixture":
                raise ValueError("fixture and replay datasets must remain synthetic fixtures")
        elif self.data_space == "synthetic" or self.verification_status == "fixture":
            raise ValueError("live dataset cannot use synthetic or fixture status")
        if any(row.data_space != self.data_space for row in self.rows):
            raise ValueError("row data space must match dataset")
        if any(row.source_document_id != self.source_document_id for row in self.rows):
            raise ValueError("row source document must match dataset")
        if any(row.source_mode != self.source_mode for row in self.rows):
            raise ValueError("row source mode must match dataset")
        if any(row.verification_status != self.verification_status for row in self.rows):
            raise ValueError("row verification status must match dataset")
        return self


class AnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["summary", "correlation", "group_mean"]
    column_name: str = Field(min_length=1)
    compare_column: str | None = None
    group_by: str | None = None


class SourceRowRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    dataset_version: int = Field(ge=1)
    source_document_id: str = Field(min_length=1)
    row_number: int = Field(ge=2)
    column_name: str = Field(min_length=1)
    source_location: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    verification_status: VerificationStatus
    source_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def _enforce_origin(self) -> "SourceRowRef":
        if self.data_space == "synthetic" and self.verification_status != "fixture":
            raise ValueError("synthetic provenance must be fixture-verified")
        if self.data_space != "synthetic" and self.verification_status == "fixture":
            raise ValueError("fixture provenance must remain synthetic")
        return self


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: int = Field(ge=1)
    operation: str = Field(min_length=1)
    column_name: str = Field(min_length=1)
    result: dict[str, Any]
    input_refs: list[SourceRowRef] = Field(min_length=1)
    output_refs: list[str] = Field(min_length=1)
    provenance: list[SourceRowRef] = Field(min_length=1)
    data_space: str = Field(min_length=1)
    source_mode: DataOrigin
    causal_interpretation_allowed: Literal[False] = False
    warnings: list[str] = Field(default_factory=list)
    created_at: float = 0.0

    @model_validator(mode="after")
    def _refs_match_space(self) -> "AnalysisResult":
        refs = self.input_refs + self.provenance
        if any(ref.data_space != self.data_space for ref in refs):
            raise ValueError("analysis input provenance data space mismatch")
        if any(ref.dataset_id != self.dataset_id or ref.dataset_version != self.dataset_version for ref in refs):
            raise ValueError("analysis dataset provenance mismatch")
        if self.source_mode in {"fixture", "replay"}:
            if self.data_space != "synthetic" or any(ref.verification_status != "fixture" for ref in refs):
                raise ValueError("fixture provenance must remain synthetic and fixture-verified")
        elif self.data_space == "synthetic":
            raise ValueError("live analysis cannot use synthetic data space")
        return self
