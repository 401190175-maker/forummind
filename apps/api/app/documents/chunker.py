"""Deterministic overlapping chunks for document search."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from collections.abc import Iterable

from app.documents.parsers import ParsedPage


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str
    chunk_id: str
    chunk_index: int
    content: str
    page_or_location: str
    char_start: int
    char_end: int


def chunk_pages(
    pages: Iterable[ParsedPage],
    max_chars: int = 1200,
    overlap: int = 150,
    *,
    document_id: str = "",
) -> list[DocumentChunk]:
    """Split each extracted page into stable chunks with bounded overlap."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be non-negative and smaller than max_chars")

    chunks: list[DocumentChunk] = []
    for page in pages:
        content = page.content.strip()
        start = 0
        while start < len(content):
            end = min(start + max_chars, len(content))
            text = content[start:end]
            identity = f"{document_id}\0{page.page_or_location}\0{start}\0{end}\0{text}"
            chunk_id = "chunk-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            chunks.append(DocumentChunk(
                document_id=document_id,
                chunk_id=chunk_id,
                chunk_index=len(chunks),
                content=text,
                page_or_location=page.page_or_location,
                char_start=start,
                char_end=end,
            ))
            if end == len(content):
                break
            start = end - overlap
    return chunks
