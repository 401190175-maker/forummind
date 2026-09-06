"""Hybrid lexical and vector retrieval for authorized document chunks."""

from __future__ import annotations

from app.knowledge.embeddings import EmbeddingIndex, EmbeddingProvider, HashEmbeddingProvider
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import SearchHit, SearchScope


class HybridSearch:
    """Combine server-filtered FTS and vector ranks with reciprocal-rank fusion."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        embedding_index: EmbeddingIndex | None = None,
        embedder: EmbeddingProvider | None = None,
        lexical_weight: float = 0.5,
        semantic_weight: float = 0.5,
        semantic_min_score: float = 0.25,
    ) -> None:
        if lexical_weight < 0 or semantic_weight < 0 or lexical_weight + semantic_weight <= 0:
            raise ValueError("retrieval weights must be non-negative and not both zero")
        if not -1.0 <= semantic_min_score <= 1.0:
            raise ValueError("semantic_min_score must be between -1 and 1")
        self.repository = repository
        self.embedding_index = embedding_index or EmbeddingIndex()
        self.embedder = embedder or HashEmbeddingProvider()
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight
        self.semantic_min_score = semantic_min_score

    def search(self, scope: SearchScope, query: str, limit: int) -> list[SearchHit]:
        query = query.strip()
        if not query:
            raise ValueError("query must be non-empty")
        if len(query) > 500:
            raise ValueError("query is too long")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")

        rows = self.repository.source_rows(scope)
        if not rows:
            return []
        self.embedding_index.rebuild(
            (row["document_id"], row["chunk_id"], self.embedder.embed(row["content"]))
            for row in rows
        )
        candidate_limit = max(limit, len(rows))
        lexical_rows = self.repository.search_rows(scope, query, candidate_limit)
        lexical_rank = {row["chunk_id"]: index for index, row in enumerate(lexical_rows, start=1)}
        semantic_hits = [
            hit for hit in self.embedding_index.query(scope, self.embedder.embed(query), candidate_limit)
            if hit.score >= self.semantic_min_score
        ]
        semantic_rank = {hit.chunk_id: index for index, hit in enumerate(semantic_hits, start=1)}
        row_by_chunk = {row["chunk_id"]: row for row in rows}

        ranked_ids = set(lexical_rank) | set(semantic_rank)
        rrf_k = 60.0
        scored = []
        for chunk_id in ranked_ids:
            score = 0.0
            if chunk_id in lexical_rank:
                score += self.lexical_weight / (rrf_k + lexical_rank[chunk_id])
            if chunk_id in semantic_rank:
                score += self.semantic_weight / (rrf_k + semantic_rank[chunk_id])
            row = row_by_chunk[chunk_id]
            scored.append((
                -score,
                lexical_rank.get(chunk_id, 10**9),
                row["chunk_index"],
                chunk_id,
                row,
                score,
            ))
        scored.sort(key=lambda item: item[:4])
        return [self._hit(row, score) for *_prefix, row, score in scored[:limit]]

    @staticmethod
    def _hit(row, score: float) -> SearchHit:
        data_space = str(row["data_space"])
        return SearchHit(
            document_id=row["document_id"],
            chunk_id=row["chunk_id"],
            content=row["content"],
            page_or_location=row["page_or_location"],
            char_start=row["char_start"],
            char_end=row["char_end"],
            score=float(score),
            source_ref=f"document:{row['document_id']}#chunk:{row['chunk_id']}",
            data_space=data_space,
            verification_status="fixture" if data_space == "synthetic" else "pending",
            source_mode="fixture" if data_space == "synthetic" else "live",
        )
