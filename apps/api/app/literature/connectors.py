"""Controlled and live literature connector implementations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.literature.schemas import LiteratureFilters, LiteratureLead, normalize_doi


class LiteratureConnectorUnavailable(RuntimeError):
    """A configured literature provider could not return a usable response."""


class _UrlFetcher:
    def get(self, url: str, *, params: Mapping[str, object] | None = None, timeout: float = 10.0):
        target = f"{url}?{urlencode(params or {})}" if params else url
        request = Request(target, headers={"Accept": "application/json", "User-Agent": "ForumMind/0.1"})
        with urlopen(request, timeout=timeout) as response:
            return {"status_code": response.status, "body": response.read().decode("utf-8")}


class CrossrefConnector:
    """Fetch public metadata through a server-owned Crossref-compatible adapter."""

    endpoint = "https://api.crossref.org/works"

    def __init__(self, *, fetcher=None, endpoint: str | None = None, timeout: float = 10.0) -> None:
        self.fetcher = fetcher or _UrlFetcher()
        self.endpoint = endpoint or self.endpoint
        self.timeout = timeout

    def search(
        self,
        query: str,
        filters: LiteratureFilters | Mapping[str, object] | None = None,
    ) -> list[LiteratureLead]:
        query = query.strip()
        if not query:
            raise ValueError("literature query must be non-empty")
        resolved = filters if isinstance(filters, LiteratureFilters) else LiteratureFilters.model_validate(filters or {})
        params: dict[str, object] = {"query": query, "rows": resolved.max_results}
        date_filters = []
        if resolved.from_year is not None:
            date_filters.append(f"from-pub-date:{resolved.from_year}-01-01")
        if resolved.until_year is not None:
            date_filters.append(f"until-pub-date:{resolved.until_year}-12-31")
        if date_filters:
            params["filter"] = ",".join(date_filters)
        try:
            raw = self.fetcher.get(self.endpoint, params=params, timeout=self.timeout)
            payload = _payload(raw)
        except Exception as exc:
            raise LiteratureConnectorUnavailable("literature provider unavailable") from exc
        items = payload.get("message", {}).get("items", [])
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise LiteratureConnectorUnavailable("literature provider returned invalid items")
        leads: list[LiteratureLead] = []
        for item in items[: resolved.max_results]:
            if isinstance(item, Mapping):
                lead = _crossref_lead(item)
                if lead is not None:
                    leads.append(lead)
        return leads


class FixtureLiteratureConnector:
    """Return deterministic records marked synthetic and fixture-only."""

    def __init__(self, records: Sequence[LiteratureLead | Mapping[str, object]]) -> None:
        self.records = [self._fixture(record) for record in records]

    def search(
        self,
        query: str,
        filters: LiteratureFilters | Mapping[str, object] | None = None,
    ) -> list[LiteratureLead]:
        query = query.strip().lower()
        if not query:
            raise ValueError("literature query must be non-empty")
        resolved = filters if isinstance(filters, LiteratureFilters) else LiteratureFilters.model_validate(filters or {})
        terms = query.split()
        matches = [
            record for record in self.records
            if all(term in f"{record.title} {record.abstract or ''}".lower() for term in terms)
        ]
        return [record.model_copy(deep=True) for record in matches[: resolved.max_results]]

    @staticmethod
    def _fixture(record: LiteratureLead | Mapping[str, object]) -> LiteratureLead:
        value = record if isinstance(record, LiteratureLead) else LiteratureLead.model_validate(record)
        return value.model_copy(update={
            "data_space": "synthetic",
            "source_mode": "fixture",
            "verification_status": "fixture",
        })


def _payload(raw) -> Mapping[str, object]:
    if isinstance(raw, Mapping) and "message" in raw:
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("response must be a mapping")
    status = int(raw.get("status_code", 200))
    if status < 200 or status >= 300:
        raise ValueError(f"provider returned HTTP {status}")
    body = raw.get("body", "")
    if not isinstance(body, str):
        raise ValueError("response body must be text")
    parsed = json.loads(body)
    if not isinstance(parsed, Mapping):
        raise ValueError("response JSON must be an object")
    return parsed


def _crossref_lead(item: Mapping[str, object]) -> LiteratureLead | None:
    doi = normalize_doi(str(item.get("DOI", "")) or None)
    raw_url = str(item.get("URL", "")).strip()
    url = raw_url or (f"https://doi.org/{doi}" if doi else "")
    title_values = item.get("title", [])
    if isinstance(title_values, str):
        title = title_values.strip()
    else:
        title = str(title_values[0]).strip() if isinstance(title_values, Sequence) and title_values else ""
    if not title or not url:
        return None
    identity = doi or url.lower()
    lead_id = "lit-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    authors = []
    raw_authors = item.get("author", [])
    if isinstance(raw_authors, Sequence) and not isinstance(raw_authors, (str, bytes)):
        for author in raw_authors:
            if isinstance(author, Mapping):
                name = " ".join(str(author.get(key, "")).strip() for key in ("given", "family") if author.get(key))
                if name:
                    authors.append(name)
    date_parts = item.get("published", item.get("published-print", {}))
    published_at = _published_year(date_parts)
    return LiteratureLead(
        lead_id=lead_id,
        title=title,
        authors=authors,
        doi=doi,
        url=url,
        published_at=published_at,
        abstract=str(item.get("abstract", "")).strip() or None,
        provider="crossref",
        source_location=f"doi:{doi}" if doi else f"url:{url}",
        data_space="verifiable_public",
        source_mode="live",
        verification_status="unverified",
    )


def _published_year(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    parts = value.get("date-parts")
    if isinstance(parts, Sequence) and parts and isinstance(parts[0], Sequence) and parts[0]:
        return str(parts[0][0])
    return None
