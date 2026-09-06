"""Literature deduplication and source verification services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re

from app.literature.schemas import LiteratureFilters, LiteratureLead, normalize_doi


class LiteratureService:
    """Deduplicate connector results without changing their provenance state."""

    def __init__(self, connector) -> None:
        self.connector = connector

    def search(
        self,
        query: str,
        filters: LiteratureFilters | Mapping[str, object] | None = None,
    ) -> list[LiteratureLead]:
        leads = self.connector.search(query, filters)
        if not isinstance(leads, Sequence) or isinstance(leads, (str, bytes)):
            raise ValueError("literature connector must return a sequence")
        unique: list[LiteratureLead] = []
        seen: set[str] = set()
        for lead in leads:
            value = lead if isinstance(lead, LiteratureLead) else LiteratureLead.model_validate(lead)
            identity = normalize_doi(value.doi) or value.url.strip().lower()
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(value)
        return unique


class EvidenceProvenance:
    """Promote a live source only after reachability and locator checks."""

    def __init__(self, fetcher, *, timeout: float = 10.0) -> None:
        self.fetcher = fetcher
        self.timeout = timeout

    def verify(self, ref: LiteratureLead) -> LiteratureLead:
        if not isinstance(ref, LiteratureLead):
            ref = LiteratureLead.model_validate(ref)
        if ref.source_mode in {"fixture", "replay"} or ref.data_space == "synthetic":
            return ref.model_copy(update={"verification_status": "fixture"})
        try:
            raw = self.fetcher.get(ref.url, params=None, timeout=self.timeout)
            status_code, body = _response(raw)
        except Exception:
            return ref.model_copy(update={"verification_status": "unavailable"})
        if 200 <= status_code < 300 and _contains_locator(ref, body):
            return ref.model_copy(update={"verification_status": "verified"})
        return ref.model_copy(update={"verification_status": "unavailable"})


def _response(raw) -> tuple[int, str]:
    if not isinstance(raw, Mapping):
        raise ValueError("source response must be a mapping")
    status_code = int(raw.get("status_code", 200))
    body = raw.get("body", "")
    if not isinstance(body, str):
        raise ValueError("source response body must be text")
    return status_code, body


def _contains_locator(ref: LiteratureLead, body: str) -> bool:
    haystack = body.casefold()
    if ref.doi and ref.doi.casefold() in haystack:
        return True
    if _compact(ref.title) in _compact(body):
        return True
    terms = [term for term in re.findall(r"[a-z0-9]+", ref.title.casefold()) if len(term) > 2]
    return bool(terms) and all(term in haystack for term in terms)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold())
