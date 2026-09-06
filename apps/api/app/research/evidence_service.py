"""Deterministic Evidence materialization from server-resolved sources."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.experiments.repository import ExperimentDatasetRepository
from app.literature.repository import LiteratureLeadRepository
from app.research.contracts import CandidateEvidenceRef
from app.research.evidence_repository import EvidenceRepository
from app.storage.sqlite_store import SQLiteStore


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_data_space: str = Field(min_length=1)
    verification_status: str = Field(min_length=1)
    applicability_boundary: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    extraction_summary: str = ""
    source_links: list[dict[str, Any]] = Field(default_factory=list)
    created_at: float
    updated_at: float


class EvidenceService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        self.repository = EvidenceRepository(store)
        self.literature = LiteratureLeadRepository(store)
        self.experiments = ExperimentDatasetRepository(store)

    def materialize(self, source_ref: str, resolved: CandidateEvidenceRef) -> EvidenceRecord:
        source_ref = source_ref.strip()
        if source_ref != resolved.source_ref:
            raise ValueError("evidence source reference mismatch")
        now = time.time()
        links: list[dict[str, Any]] = [{"source_ref": source_ref, "locator": resolved.model_dump(mode="json")}]
        extraction = ""
        locator = resolved.page_or_location
        source_type = resolved.source_type
        source_space = resolved.data_space
        if source_ref.startswith("literature:"):
            lead = self.literature.get(source_ref)
            if lead is None:
                raise ValueError("literature source does not exist")
            locator = lead.source_location
            extraction = lead.abstract or lead.title
            source_type = "literature"
            source_space = lead.data_space
        elif source_ref.startswith("analysis:"):
            analysis = self.experiments.get_analysis(source_ref.removeprefix("analysis:"))
            if analysis is None:
                raise ValueError("analysis source does not exist")
            locator = f"{analysis.dataset_id} v{analysis.dataset_version}"
            extraction = str(analysis.result)
            source_type = "experiment"
            source_space = analysis.data_space
            links = [
                {"source_ref": ref.source_ref, "locator": ref.model_dump(mode="json")}
                for ref in analysis.provenance
            ] or links
        record = EvidenceRecord(
            evidence_id="evidence-" + hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:24],
            source_ref=source_ref,
            source_type=source_type,
            source_data_space=source_space,
            verification_status=resolved.verification_status,
            applicability_boundary="source-specific; does not establish a universal claim",
            locator=locator,
            extraction_summary=extraction,
            source_links=links,
            created_at=now,
            updated_at=now,
        )
        self.repository.save(record.model_dump(mode="python"), links)
        return record

    def persist_candidate_sources(
        self, candidate_id: str, refs: list[str], resolved: Mapping[str, CandidateEvidenceRef],
    ) -> list[EvidenceRecord]:
        records = [self.materialize(source_ref, resolved[source_ref]) for source_ref in refs]
        self.repository.link_candidate(candidate_id, refs)
        return records

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        record = self.repository.get(evidence_id)
        return None if record is None else EvidenceRecord.model_validate({**record, "source_links": record.get("source_links", [])})
