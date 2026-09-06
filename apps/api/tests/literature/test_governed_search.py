"""Governed literature search keeps live and fixture provenance separate."""

import pytest

from app.literature.connectors import FixtureLiteratureConnector
from app.literature.schemas import LiteratureLead
from app.literature.service import EvidenceProvenance, LiteratureService
from app.literature.integration import GovernedLiteratureSearch


def _fixture_service() -> LiteratureService:
    return LiteratureService(FixtureLiteratureConnector([
        LiteratureLead(
            lead_id="fixture-a", title="Foam concrete", url="https://fixture.test/a",
            source_location="url:https://fixture.test/a", data_space="synthetic",
            source_mode="fixture", verification_status="fixture",
        ),
    ]))


def test_fixture_search_is_explicitly_synthetic_and_fixture_verified() -> None:
    result = GovernedLiteratureSearch(_fixture_service()).search(
        "foam", source_mode="fixture",
    )

    assert len(result) == 1
    assert result[0].data_space == "synthetic"
    assert result[0].source_mode == "fixture"
    assert result[0].verification_status == "fixture"


def test_live_search_rejects_a_fixture_connector_instead_of_relabeling_it() -> None:
    with pytest.raises(ValueError, match="source mode"):
        GovernedLiteratureSearch(_fixture_service()).search(
            "foam", source_mode="live",
        )


def test_verified_search_requires_a_server_owned_verifier() -> None:
    with pytest.raises(ValueError, match="verifier"):
        GovernedLiteratureSearch(_fixture_service()).search(
            "foam", source_mode="fixture", verify=True,
        )
