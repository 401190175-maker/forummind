"""Controlled-source contracts for literature metadata and provenance."""

import importlib.util

from app.literature.connectors import CrossrefConnector, FixtureLiteratureConnector
from app.literature.schemas import LiteratureLead
from app.literature.service import EvidenceProvenance, LiteratureService


def test_literature_package_exposes_the_p3_connector_boundary():
    try:
        module = importlib.util.find_spec("app.literature.connectors")
    except ModuleNotFoundError:
        module = None

    assert module is not None


class _CrossrefFetcher:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return self.payload


class _SourceFetcher:
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body

    def get(self, url, *, params=None, timeout=0):
        return {"status_code": self.status_code, "body": self.body}


def _crossref_payload():
    return {
        "message": {
            "items": [
                {
                    "title": ["Foam concrete pore structure"],
                    "DOI": "10.1000/ABC.1",
                    "URL": "https://doi.org/10.1000/ABC.1",
                    "author": [{"given": "A", "family": "Researcher"}],
                    "published": {"date-parts": [[2024, 5, 1]]},
                    "abstract": "Pore structure affects strength.",
                },
                {
                    "title": ["Duplicate DOI record"],
                    "DOI": "10.1000/abc.1",
                    "URL": "https://doi.org/10.1000/abc.1",
                },
            ]
        }
    }


def test_crossref_connector_preserves_live_metadata_and_service_dedupes_doi():
    fetcher = _CrossrefFetcher(_crossref_payload())
    connector = CrossrefConnector(fetcher=fetcher)

    leads = LiteratureService(connector).search("foam concrete")

    assert len(leads) == 1
    assert leads[0].doi == "10.1000/abc.1"
    assert leads[0].source_mode == "live"
    assert leads[0].data_space == "verifiable_public"
    assert leads[0].verification_status == "unverified"
    assert leads[0].source_location == "doi:10.1000/abc.1"
    assert fetcher.calls[0][1]["query"] == "foam concrete"


def test_fixture_connector_cannot_become_live_or_verified():
    lead = LiteratureLead(
        lead_id="fixture-1", title="Controlled record", authors=["Fixture Author"],
        doi="10.5555/fixture", url="https://example.test/fixture",
        source_location="doi:10.5555/fixture", data_space="synthetic",
        source_mode="fixture", verification_status="fixture",
    )
    fixture = FixtureLiteratureConnector([lead])
    returned = fixture.search("controlled")[0]

    verified = EvidenceProvenance(_SourceFetcher(200, "10.5555/fixture Controlled record")).verify(returned)

    assert verified.source_mode == "fixture"
    assert verified.data_space == "synthetic"
    assert verified.verification_status == "fixture"


def test_live_provenance_requires_reachable_and_locatable_source():
    lead = LiteratureLead(
        lead_id="live-1", title="Foam concrete pore structure", authors=[],
        doi="10.1000/abc.1", url="https://doi.org/10.1000/abc.1",
        source_location="doi:10.1000/abc.1", data_space="verifiable_public",
        source_mode="live", verification_status="unverified",
    )

    verified = EvidenceProvenance(_SourceFetcher(200, "10.1000/abc.1 Foam concrete pore structure")).verify(lead)
    unavailable = EvidenceProvenance(_SourceFetcher(404, "missing")).verify(lead)

    assert verified.verification_status == "verified"
    assert unavailable.verification_status == "unavailable"


def test_crossref_connector_keeps_a_string_title_as_one_title():
    connector = CrossrefConnector(fetcher=_CrossrefFetcher({
        "message": {"items": [{
            "title": "Foam concrete title",
            "DOI": "10.1000/string-title",
            "URL": "https://doi.org/10.1000/string-title",
        }]}
    }))

    leads = connector.search("foam concrete")

    assert leads[0].title == "Foam concrete title"


def test_live_provenance_can_locate_a_chinese_title_without_ascii_tokens():
    lead = LiteratureLead(
        lead_id="live-cn", title="泡沫混凝土孔结构", authors=[],
        url="https://example.test/paper", source_location="url:https://example.test/paper",
        data_space="verifiable_public", source_mode="live", verification_status="unverified",
    )

    verified = EvidenceProvenance(_SourceFetcher(200, "研究结果：泡沫混凝土孔结构发生变化。")).verify(lead)

    assert verified.verification_status == "verified"
