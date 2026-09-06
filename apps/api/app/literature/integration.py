"""Server-owned literature search entry point for future tool consumers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from app.literature.schemas import LiteratureFilters, LiteratureLead, SourceMode
from app.literature.service import EvidenceProvenance, LiteratureService


class GovernedLiteratureSearch:
    """Keep connector origin and requested research mode aligned."""

    def __init__(
        self,
        service: LiteratureService,
        *,
        verifier: EvidenceProvenance | None = None,
    ) -> None:
        self.service = service
        self.verifier = verifier

    def search(
        self,
        query: str,
        filters: LiteratureFilters | Mapping[str, object] | None = None,
        *,
        source_mode: SourceMode = "live",
        verify: bool = False,
    ) -> list[LiteratureLead]:
        if source_mode not in {"live", "fixture", "replay"}:
            raise ValueError("unsupported literature source mode")
        if verify and self.verifier is None:
            raise ValueError("a server-owned literature verifier is required")

        leads = self.service.search(query, filters)
        expected_space = "synthetic" if source_mode in {"fixture", "replay"} else "verifiable_public"
        for lead in leads:
            if lead.source_mode != source_mode:
                raise ValueError("literature source mode does not match requested source mode")
            if lead.data_space != expected_space:
                raise ValueError("literature data space does not match requested source mode")
            if source_mode in {"fixture", "replay"} and lead.verification_status != "fixture":
                raise ValueError("fixture literature must remain fixture verified")
            if source_mode == "live" and lead.verification_status == "fixture":
                raise ValueError("live literature cannot use fixture verification")

        if verify:
            return [self.verifier.verify(lead) for lead in leads]
        return leads
