"""Metadata and provenance contracts for literature sources."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceMode = Literal["live", "fixture", "replay"]
LiteratureVerificationStatus = Literal["unverified", "verified", "unavailable", "fixture"]


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized or None


class LiteratureFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_year: int | None = Field(default=None, ge=1900, le=2100)
    until_year: int | None = Field(default=None, ge=1900, le=2100)
    max_results: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _valid_range(self) -> "LiteratureFilters":
        if self.from_year is not None and self.until_year is not None and self.from_year > self.until_year:
            raise ValueError("from_year must not be after until_year")
        return self


class LiteratureLead(BaseModel):
    """A source lead whose status is independent from model-generated text."""

    model_config = ConfigDict(extra="forbid")

    lead_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    url: str = Field(min_length=1)
    published_at: str | None = None
    abstract: str | None = None
    provider: str = Field(default="crossref", min_length=1)
    source_location: str = Field(min_length=1)
    source_ref: str = ""
    data_space: Literal["verifiable_public", "synthetic"]
    source_mode: SourceMode
    verification_status: LiteratureVerificationStatus

    @field_validator("doi", mode="before")
    @classmethod
    def _normalize_doi(cls, value: str | None) -> str | None:
        return normalize_doi(value)

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("literature URL must use http or https")
        return value

    @model_validator(mode="after")
    def _enforce_origin_and_reference(self) -> "LiteratureLead":
        if not self.source_ref:
            self.source_ref = f"literature:{self.lead_id}"
        if self.source_mode in {"fixture", "replay"}:
            if self.data_space != "synthetic" or self.verification_status != "fixture":
                raise ValueError("fixture and replay literature must remain synthetic fixtures")
        elif self.data_space != "verifiable_public":
            raise ValueError("live literature must use verifiable_public data space")
        elif self.verification_status == "fixture":
            raise ValueError("live literature cannot use fixture verification status")
        return self
