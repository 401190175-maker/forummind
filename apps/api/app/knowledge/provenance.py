"""Project P3 source records into the formal Evidence contract.

These adapters only project already verified metadata. They never infer a
source, change a verification state, or turn model text into Evidence.
"""

from __future__ import annotations

from app.domain.schemas.common import DataSpace, SourceType, VerificationStatus
from app.domain.schemas.evidence import DataCategory, Evidence
from app.experiments.schemas import SourceRowRef
from app.knowledge.schemas import SearchHit
from app.literature.schemas import LiteratureLead


def _boundary(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("applicability_boundary must be non-empty")
    return value.strip()


def _verification(value: str, *, fixture: bool = False) -> VerificationStatus:
    if fixture:
        return VerificationStatus.LEAD
    return {
        "pending": VerificationStatus.PENDING,
        "unverified": VerificationStatus.PENDING,
        "verified": VerificationStatus.VERIFIED,
        "unavailable": VerificationStatus.LEAD,
    }.get(value, VerificationStatus.PENDING)


def search_hit_to_evidence(hit: SearchHit, *, applicability_boundary: str) -> Evidence:
    """Project one located uploaded-document hit without changing its status."""

    boundary = _boundary(applicability_boundary)
    fixture = hit.source_mode in {"fixture", "replay"} or hit.data_space == "synthetic"
    return Evidence(
        source_type=SourceType.SYNTHETIC_DEMO if fixture else SourceType.USER_UPLOADED,
        data_category=DataCategory.SYNTHETIC if fixture else DataCategory.TEXT,
        verification_status=_verification(hit.verification_status, fixture=fixture),
        applicability_boundary=boundary,
        source_location=f"{hit.page_or_location} [{hit.char_start}:{hit.char_end}]",
        data_space=DataSpace.SYNTHETIC if fixture else DataSpace(hit.data_space),
        extraction_summary=hit.content,
    )


def literature_lead_to_evidence(
    lead: LiteratureLead,
    *,
    applicability_boundary: str,
) -> Evidence:
    """Project a literature lead; only a verified live lead becomes verified."""

    boundary = _boundary(applicability_boundary)
    fixture = lead.source_mode in {"fixture", "replay"} or lead.data_space == "synthetic"
    return Evidence(
        source_type=SourceType.SYNTHETIC_DEMO if fixture else SourceType.LITERATURE,
        data_category=DataCategory.SYNTHETIC if fixture else DataCategory.TEXT,
        verification_status=_verification(lead.verification_status, fixture=fixture),
        applicability_boundary=boundary,
        source_location=lead.source_location,
        data_space=DataSpace.SYNTHETIC if fixture else DataSpace.VERIFIABLE_PUBLIC,
        extraction_summary=lead.abstract,
    )


def experiment_row_to_evidence(
    ref: SourceRowRef,
    *,
    applicability_boundary: str,
    data_category: DataCategory = DataCategory.NUMERIC,
) -> Evidence:
    """Project a dataset row/column reference with an exact source locator."""

    boundary = _boundary(applicability_boundary)
    fixture = ref.data_space == "synthetic" or ref.verification_status == "fixture"
    return Evidence(
        source_type=SourceType.SYNTHETIC_DEMO if fixture else SourceType.EXPERIMENT,
        data_category=DataCategory.SYNTHETIC if fixture else data_category,
        verification_status=_verification(ref.verification_status, fixture=fixture),
        applicability_boundary=boundary,
        source_location=f"{ref.source_location} column {ref.column_name}",
        data_space=DataSpace.SYNTHETIC if fixture else DataSpace(ref.data_space),
        samples=f"{ref.dataset_id} v{ref.dataset_version} row {ref.row_number}",
    )
