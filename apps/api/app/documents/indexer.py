"""Synchronous, restartable document parse and indexing workflow."""

from __future__ import annotations

import time

from app.documents.chunker import chunk_pages
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.documents.storage import DocumentStorage
from app.documents.parsers import parse_document


class Indexer:
    """Process uploaded documents and persist a recoverable index state."""

    def __init__(self, documents: DocumentRepository, storage: DocumentStorage) -> None:
        self.documents = documents
        self.storage = storage

    def process(self, document_id: str) -> DocumentRecord:
        document = self.documents.get(document_id)
        if document is None:
            raise KeyError(document_id)
        existing_job = self.documents.get_index_job(document_id)
        if document.status == "ready" and existing_job is not None and existing_job.status == "ready":
            return document

        retry_count = existing_job.retry_count + 1 if existing_job and existing_job.status == "failed" else 0
        started_at = time.time()
        self.documents.set_status(document_id, "processing", updated_at=started_at)
        self.documents.save_index_job(DocumentIndexJob(
            document_id=document_id,
            status="processing",
            error_code="",
            retry_count=retry_count,
            started_at=started_at,
            finished_at=None,
            updated_at=started_at,
        ))
        try:
            pages = parse_document(self.storage.path_for(document), document.mime_type)
            chunks = chunk_pages(pages, document_id=document.document_id)
            finished_at = time.time()
            with self.documents.store.transaction():
                self.documents.replace_chunks(document_id, chunks)
                self.documents.set_status(document_id, "ready", updated_at=finished_at)
                self.documents.save_index_job(DocumentIndexJob(
                    document_id=document_id,
                    status="ready",
                    error_code="",
                    retry_count=retry_count,
                    started_at=started_at,
                    finished_at=finished_at,
                    updated_at=finished_at,
                ))
        except Exception:
            finished_at = time.time()
            with self.documents.store.transaction():
                self.documents.set_status(document_id, "failed", updated_at=finished_at)
                self.documents.save_index_job(DocumentIndexJob(
                    document_id=document_id,
                    status="failed",
                    error_code="document_processing",
                    retry_count=retry_count,
                    started_at=started_at,
                    finished_at=finished_at,
                    updated_at=finished_at,
                ))
        result = self.documents.get(document_id)
        assert result is not None
        return result

    def recover_processing(self) -> int:
        """Return interrupted processing jobs to the upload queue."""
        processing = self.documents.list_by_status("processing")
        now = time.time()
        with self.documents.store.transaction():
            for document in processing:
                self.documents.set_status(document.document_id, "uploaded", updated_at=now)
                job = self.documents.get_index_job(document.document_id)
                if job is not None:
                    self.documents.save_index_job(job.model_copy(update={
                        "status": "uploaded",
                        "finished_at": None,
                        "updated_at": now,
                    }))
        return len(processing)
