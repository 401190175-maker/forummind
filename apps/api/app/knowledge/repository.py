"""SQLite FTS persistence for parsed document chunks."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
import re
from typing import Any

from app.knowledge.schemas import SearchScope
from app.storage.sqlite_store import SQLiteStore


_FTS_TERM_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")


def _disjunctive_query(query: str) -> str:
    terms: list[str] = []
    seen: set[str] = set()
    for match in _FTS_TERM_PATTERN.finditer(query):
        term = match.group(0)
        normalized = term.casefold()
        if len(term) < 3 or normalized in {"and", "or", "not"} or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(f'"{term.replace(chr(34), chr(34) * 2)}"')
    return " OR ".join(terms)


class KnowledgeRepository:
    """Maintain and query the local full-text index for document chunks."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        with self.store.transaction() as connection:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts
                USING fts5(chunk_id UNINDEXED, content, tokenize='trigram')
                """
            )

    def rebuild_index(self) -> None:
        """Rebuild from durable chunks so restart and external writes stay safe."""

        with self.store.transaction() as connection:
            connection.execute("DELETE FROM document_chunks_fts")
            connection.execute(
                """
                INSERT INTO document_chunks_fts (chunk_id, content)
                SELECT chunk_id, content FROM document_chunks
                """
            )

    def search_rows(self, scope: SearchScope, query: str, limit: int) -> list[sqlite3.Row]:
        """Return rows already filtered by every server-owned scope dimension."""

        if not scope.allowed_document_ids:
            return []
        self.rebuild_index()
        document_placeholders = ", ".join("?" for _ in scope.allowed_document_ids)
        parameters: Sequence[Any] = (
            query,
            scope.task_id,
            scope.group_chat_id,
            scope.data_space,
            scope.group_chat_id,
            scope.data_space,
            *scope.allowed_document_ids,
            limit,
        )
        statement = f"""
            SELECT c.document_id, c.chunk_id, c.content, c.page_or_location,
                   c.char_start, c.char_end,
                   d.data_space,
                   -bm25(document_chunks_fts) AS score
            FROM document_chunks_fts
            JOIN document_chunks AS c ON c.chunk_id = document_chunks_fts.chunk_id
            JOIN documents AS d ON d.document_id = c.document_id
            JOIN task_documents AS td ON td.document_id = d.document_id
            JOIN research_tasks AS t ON t.task_id = td.task_id
            JOIN document_index_jobs AS j ON j.document_id = d.document_id
            WHERE document_chunks_fts MATCH ?
              AND t.task_id = ?
              AND t.group_chat_id = ?
              AND t.data_space = ?
              AND d.group_chat_id = ?
              AND d.data_space = ?
              AND d.status = 'ready'
              AND j.status = 'ready'
              AND d.document_id IN ({document_placeholders})
            ORDER BY bm25(document_chunks_fts), c.chunk_index, c.chunk_id
            LIMIT ?
        """
        with self.store.locked() as connection:
            try:
                rows = connection.execute(statement, parameters).fetchall()
            except sqlite3.OperationalError:
                # A malformed FTS expression should remain a safe empty search.
                safe_query = '"' + query.replace('"', '""') + '"'
                fallback = list(parameters)
                fallback[0] = safe_query
                rows = connection.execute(statement, fallback).fetchall()
            if rows:
                return rows
            broad_query = _disjunctive_query(query)
            if not broad_query:
                return []
            fallback = list(parameters)
            fallback[0] = broad_query
            return connection.execute(statement, fallback).fetchall()

    def source_rows(self, scope: SearchScope) -> list[sqlite3.Row]:
        """Return every currently searchable chunk in the trusted scope."""

        if not scope.allowed_document_ids:
            return []
        placeholders = ", ".join("?" for _ in scope.allowed_document_ids)
        statement = f"""
            SELECT c.document_id, c.chunk_id, c.chunk_index, c.content,
                   c.page_or_location, c.char_start, c.char_end, d.data_space
            FROM document_chunks AS c
            JOIN documents AS d ON d.document_id = c.document_id
            JOIN task_documents AS td ON td.document_id = d.document_id
            JOIN research_tasks AS t ON t.task_id = td.task_id
            JOIN document_index_jobs AS j ON j.document_id = d.document_id
            WHERE t.task_id = ?
              AND t.group_chat_id = ?
              AND t.data_space = ?
              AND d.group_chat_id = ?
              AND d.data_space = ?
              AND d.status = 'ready'
              AND j.status = 'ready'
              AND d.document_id IN ({placeholders})
            ORDER BY c.chunk_index, c.chunk_id
        """
        parameters: Sequence[Any] = (
            scope.task_id,
            scope.group_chat_id,
            scope.data_space,
            scope.group_chat_id,
            scope.data_space,
            *scope.allowed_document_ids,
        )
        with self.store.locked() as connection:
            return connection.execute(statement, parameters).fetchall()
