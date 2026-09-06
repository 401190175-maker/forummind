"""Small dependency-free embedding and vector-index primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import math
import re

from app.knowledge.schemas import SearchScope


class EmbeddingProvider:
    """Provider boundary used by the hybrid search service."""

    dimensions: int

    def embed(self, text: str) -> tuple[float, ...]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embedding suitable for indexing and controlled tests."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions < 2:
            raise ValueError("dimensions must be at least 2")
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        vector = [0.0] * self.dimensions
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        return tuple(vector)


@dataclass(frozen=True)
class EmbeddingHit:
    document_id: str
    chunk_id: str
    score: float


class EmbeddingIndex:
    """In-memory vector index rebuilt from server-owned durable chunks."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, tuple[float, ...]]] = {}

    def upsert(self, document_id: str, chunk_id: str, vector: Iterable[float]) -> None:
        normalized = tuple(float(value) for value in vector)
        if not document_id.strip() or not chunk_id.strip():
            raise ValueError("document_id and chunk_id must be non-empty")
        if not normalized or any(not math.isfinite(value) for value in normalized):
            raise ValueError("vector must contain finite values")
        self._entries[chunk_id] = (document_id, normalized)

    def rebuild(self, entries: Iterable[tuple[str, str, Iterable[float]]]) -> None:
        rebuilt: dict[str, tuple[str, tuple[float, ...]]] = {}
        for document_id, chunk_id, vector in entries:
            normalized = tuple(float(value) for value in vector)
            if not document_id.strip() or not chunk_id.strip():
                raise ValueError("document_id and chunk_id must be non-empty")
            if not normalized or any(not math.isfinite(value) for value in normalized):
                raise ValueError("vector must contain finite values")
            rebuilt[chunk_id] = (document_id, normalized)
        self._entries = rebuilt

    def query(self, scope: SearchScope, vector: Iterable[float], limit: int) -> list[EmbeddingHit]:
        query = tuple(float(value) for value in vector)
        if not query or any(not math.isfinite(value) for value in query):
            raise ValueError("query vector must contain finite values")
        if limit < 1:
            raise ValueError("limit must be positive")
        allowed = set(scope.allowed_document_ids)
        query_norm = math.sqrt(sum(value * value for value in query))
        hits: list[EmbeddingHit] = []
        for chunk_id, (document_id, candidate) in self._entries.items():
            if document_id not in allowed or len(candidate) != len(query):
                continue
            candidate_norm = math.sqrt(sum(value * value for value in candidate))
            denominator = candidate_norm * query_norm
            score = 0.0 if denominator == 0 else sum(
                left * right for left, right in zip(candidate, query)
            ) / denominator
            hits.append(EmbeddingHit(document_id=document_id, chunk_id=chunk_id, score=score))
        hits.sort(key=lambda hit: (-hit.score, hit.document_id, hit.chunk_id))
        return hits[:limit]
