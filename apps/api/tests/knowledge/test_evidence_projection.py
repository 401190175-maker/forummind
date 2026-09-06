"""P3 sources must project into the formal Evidence contract without fabrication."""

import pytest

from app.domain.schemas.common import DataSpace, SourceType, VerificationStatus
from app.domain.schemas.evidence import DataCategory, Evidence
from app.experiments.schemas import SourceRowRef
from app.knowledge.provenance import experiment_row_to_evidence, literature_lead_to_evidence, search_hit_to_evidence
from app.knowledge.schemas import SearchHit
from app.literature.schemas import LiteratureLead


def test_uploaded_search_hit_projects_as_pending_located_evidence() -> None:
    hit = SearchHit(
        document_id="doc-a", chunk_id="chunk-a", content="strength is 3.2 MPa",
        page_or_location="page 2", char_start=10, char_end=29, score=0.9,
        source_ref="document:doc-a#chunk:chunk-a", data_space="desensitized_real",
    )

    evidence = search_hit_to_evidence(hit, applicability_boundary="current task documents only")

    assert isinstance(evidence, Evidence)
    assert evidence.source_type is SourceType.USER_UPLOADED
    assert evidence.data_category is DataCategory.TEXT
    assert evidence.verification_status is VerificationStatus.PENDING
    assert evidence.data_space is DataSpace.DESENSITIZED_REAL
    assert evidence.source_location == "page 2 [10:29]"


def test_verified_public_literature_projects_as_located_verified_evidence() -> None:
    lead = LiteratureLead(
        lead_id="lit-a", title="Foam concrete strength", authors=["A. Author"],
        doi="10.1000/example", url="https://doi.org/10.1000/example",
        source_location="doi:10.1000/example", data_space="verifiable_public",
        source_mode="live", verification_status="verified",
    )

    evidence = literature_lead_to_evidence(lead, applicability_boundary="metadata and abstract only")

    assert evidence.source_type is SourceType.LITERATURE
    assert evidence.data_category is DataCategory.TEXT
    assert evidence.verification_status is VerificationStatus.VERIFIED
    assert evidence.data_space is DataSpace.VERIFIABLE_PUBLIC
    assert evidence.source_location == "doi:10.1000/example"


def test_fixture_literature_cannot_project_as_verified_real_evidence() -> None:
    lead = LiteratureLead(
        lead_id="fixture-a", title="Fixture paper", url="https://fixture.test/paper",
        source_location="url:https://fixture.test/paper", data_space="synthetic",
        source_mode="fixture", verification_status="fixture",
    )

    evidence = literature_lead_to_evidence(lead, applicability_boundary="fixture regression only")

    assert evidence.source_type is SourceType.SYNTHETIC_DEMO
    assert evidence.data_category is DataCategory.SYNTHETIC
    assert evidence.verification_status is VerificationStatus.LEAD
    assert evidence.data_space is DataSpace.SYNTHETIC


def test_experiment_row_projects_row_and_column_location() -> None:
    row = SourceRowRef(
        dataset_id="dataset-a", dataset_version=2, source_document_id="doc-exp",
        row_number=7, column_name="strength", source_location="doc-exp:row:7",
        data_space="desensitized_real", verification_status="verified",
        source_ref="dataset:dataset-a:v2:row:7:column:strength",
    )

    evidence = experiment_row_to_evidence(row, applicability_boundary="observational result only")

    assert evidence.source_type is SourceType.EXPERIMENT
    assert evidence.data_category is DataCategory.NUMERIC
    assert evidence.verification_status is VerificationStatus.VERIFIED
    assert evidence.source_location == "doc-exp:row:7 column strength"
    assert evidence.samples == "dataset-a v2 row 7"


def test_unlocated_projection_is_rejected_instead_of_fabricating_evidence() -> None:
    hit = SearchHit(
        document_id="doc-a", chunk_id="chunk-a", content="text", page_or_location="page 1",
        char_start=0, char_end=4, score=0.1, source_ref="document:doc-a#chunk:chunk-a",
        data_space="real",
    )

    with pytest.raises(ValueError, match="applicability_boundary"):
        search_hit_to_evidence(hit, applicability_boundary=" ")
