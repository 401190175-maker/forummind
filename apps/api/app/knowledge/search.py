"""Application service for bounded, located knowledge search."""

from __future__ import annotations

from app.knowledge.hybrid_search import HybridSearch
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import SearchHit, SearchScope


class KnowledgeSearch:
    """Translate FTS rows into stable source references for tool consumers."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        max_limit: int = 50,
        hybrid_search: HybridSearch | None = None,
    ) -> None:
        if max_limit < 1:
            raise ValueError("max_limit must be positive")
        self.repository = repository
        self.max_limit = max_limit
        self.hybrid_search = hybrid_search or HybridSearch(repository)

    def search(self, scope: SearchScope, query: str, limit: int) -> list[SearchHit]:
        query = query.strip()
        if not query:
            raise ValueError("query must be non-empty")
        if len(query) > 500:
            raise ValueError("query is too long")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        return self.hybrid_search.search(scope, query, min(limit, self.max_limit))
