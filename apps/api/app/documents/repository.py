"""SQLite repository for document metadata."""

from __future__ import annotations

from collections.abc import Mapping
import time

from app.documents.chunker import DocumentChunk
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.storage.sqlite_store import SQLiteStore


class DocumentRepository:
    """Persist document metadata and enforce group-scoped reads."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, record: DocumentRecord | Mapping[str, object]) -> DocumentRecord:
        document = record if isinstance(record, DocumentRecord) else DocumentRecord.model_validate(record)

        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO documents
                    (document_id, group_chat_id, filename, mime_type, size_bytes,
                     sha256, storage_key, data_space, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.document_id,
                    document.group_chat_id,
                    document.filename,
                    document.mime_type,
                    document.size_bytes,
                    document.sha256,
                    document.storage_key,
                    document.data_space,
                    document.status,
                    document.created_at,
                    document.updated_at,
                ),
            )

        if self.store.in_transaction:
            operation(self.store.connection())
        else:
            with self.store.transaction() as connection:
                operation(connection)
        return document

    def get(self, document_id: str) -> DocumentRecord | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def get_for_group(self, document_id: str, group_chat_id: str) -> DocumentRecord | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM documents
                WHERE document_id = ? AND group_chat_id = ?
                """,
                (document_id, group_chat_id),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def list_for_group(self, group_chat_id: str) -> list[DocumentRecord]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT * FROM documents
                WHERE group_chat_id = ?
                ORDER BY created_at, document_id
                """,
                (group_chat_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def find_by_hash(self, group_chat_id: str, sha256: str) -> DocumentRecord | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM documents
                WHERE group_chat_id = ? AND sha256 = ?
                ORDER BY created_at, document_id
                LIMIT 1
                """,
                (group_chat_id, sha256),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def set_status(self, document_id: str, status: str, *, updated_at: float | None = None) -> None:
        timestamp = time.time() if updated_at is None else updated_at

        def operation(connection) -> None:
            cursor = connection.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE document_id = ?",
                (status, timestamp, document_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(document_id)

        if self.store.in_transaction:
            operation(self.store.connection())
        else:
            with self.store.transaction() as connection:
                operation(connection)

    def list_by_status(self, status: str) -> list[DocumentRecord]:
        with self.store.locked() as connection:
            rows = connection.execute(
                "SELECT * FROM documents WHERE status = ? ORDER BY updated_at, document_id",
                (status,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def replace_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> None:
        def operation(connection) -> None:
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            connection.executemany(
                """
                INSERT INTO document_chunks
                    (document_id, chunk_id, chunk_index, content,
                     page_or_location, char_start, char_end)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.document_id,
                        chunk.chunk_id,
                        chunk.chunk_index,
                        chunk.content,
                        chunk.page_or_location,
                        chunk.char_start,
                        chunk.char_end,
                    )
                    for chunk in chunks
                ],
            )

        if self.store.in_transaction:
            operation(self.store.connection())
        else:
            with self.store.transaction() as connection:
                operation(connection)

    def list_chunks(self, document_id: str) -> list[DocumentChunk]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT document_id, chunk_id, chunk_index, content,
                       page_or_location, char_start, char_end
                FROM document_chunks
                WHERE document_id = ? ORDER BY chunk_index, chunk_id
                """,
                (document_id,),
            ).fetchall()
        return [DocumentChunk(**dict(row)) for row in rows]

    def save_index_job(self, job: DocumentIndexJob) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO document_index_jobs
                    (document_id, status, error_code, retry_count,
                     started_at, finished_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    status = excluded.status,
                    error_code = excluded.error_code,
                    retry_count = excluded.retry_count,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    updated_at = excluded.updated_at
                """,
                (
                    job.document_id,
                    job.status,
                    job.error_code,
                    job.retry_count,
                    job.started_at,
                    job.finished_at,
                    job.updated_at,
                ),
            )

        if self.store.in_transaction:
            operation(self.store.connection())
        else:
            with self.store.transaction() as connection:
                operation(connection)

    def get_index_job(self, document_id: str) -> DocumentIndexJob | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT * FROM document_index_jobs WHERE document_id = ?", (document_id,)
            ).fetchone()
        return DocumentIndexJob.model_validate(dict(row)) if row is not None else None

    @staticmethod
    def _from_row(row) -> DocumentRecord:
        return DocumentRecord.model_validate(dict(row))
