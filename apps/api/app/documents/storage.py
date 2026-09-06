"""Controlled local file storage for research documents."""

from __future__ import annotations

import hashlib
from pathlib import Path
import time
from uuid import uuid4

from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentRecord


SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


class DocumentStorageError(ValueError):
    """Base error for rejected document uploads."""


class DocumentTooLargeError(DocumentStorageError):
    """The upload exceeds the configured byte limit."""


class UnsupportedDocumentTypeError(DocumentStorageError):
    """The upload MIME type or extension is not supported."""


class DocumentStorage:
    """Write bytes below one configured root and store only generated keys."""

    def __init__(
        self,
        root: str | Path,
        repository: DocumentRepository,
        *,
        max_upload_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.root = Path(root).resolve()
        self.repository = repository
        self.max_upload_bytes = max(1, max_upload_bytes)

    def save(
        self,
        group_chat_id: str,
        filename: str,
        data: bytes,
        data_space: str,
        mime_type: str | None = None,
    ) -> DocumentRecord:
        if len(data) > self.max_upload_bytes:
            raise DocumentTooLargeError("document exceeds configured size limit")
        safe_filename = self._filename(filename)
        normalized_mime = (mime_type or MIME_BY_EXTENSION[Path(safe_filename).suffix.lower()]).strip().lower()
        if normalized_mime not in SUPPORTED_MIME_TYPES:
            raise UnsupportedDocumentTypeError("unsupported document MIME type")
        if not data:
            raise DocumentStorageError("document must not be empty")
        if not data_space.strip():
            raise DocumentStorageError("data_space must be non-empty")

        digest = hashlib.sha256(data).hexdigest()
        existing = self.repository.find_by_hash(group_chat_id, digest)
        if existing is not None:
            return existing

        suffix = Path(safe_filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            suffix = ""
        storage_key = f"documents/{uuid4().hex}{suffix}"
        path = self._path_for_key(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        now = time.time()
        record = DocumentRecord(
            document_id=f"doc-{uuid4().hex}",
            group_chat_id=group_chat_id,
            filename=safe_filename,
            mime_type=normalized_mime,
            size_bytes=len(data),
            sha256=digest,
            storage_key=storage_key,
            data_space=data_space.strip(),
            status="uploaded",
            created_at=now,
            updated_at=now,
        )
        try:
            return self.repository.save(record)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def path_for(self, record: DocumentRecord) -> Path:
        return self._path_for_key(record.storage_key)

    def _path_for_key(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise DocumentStorageError("storage key escapes configured root")
        return candidate

    @staticmethod
    def _filename(filename: str) -> str:
        value = (filename or "").replace("\\", "/").split("/")[-1].strip()
        if not value or value in {".", ".."}:
            raise DocumentStorageError("filename must be non-empty")
        suffix = Path(value).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise UnsupportedDocumentTypeError("unsupported document extension")
        return value[:255]
