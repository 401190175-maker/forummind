"""HTTP API for group-scoped research document uploads."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.documents.repository import DocumentRepository
from app.documents.indexer import Indexer
from app.documents.schemas import DocumentRecord
from app.documents.storage import (
    DocumentStorage,
    DocumentStorageError,
    DocumentTooLargeError,
    UnsupportedDocumentTypeError,
)
from app.group_chats.messages import append_chat_message
from app.storage.repositories import GroupChatRepository
from app.storage.sqlite_store import SQLiteStore
from app.auth.dependencies import auth_required, get_current_user
from app.permissions.policy import authorize_group_access


router = APIRouter(tags=["documents"])
_store: SQLiteStore | None = None
_documents: DocumentRepository | None = None
_storage: DocumentStorage | None = None
_groups: GroupChatRepository | None = None


def configure_persistence(
    store: SQLiteStore | None,
    root: str | Path | None = None,
    *,
    max_upload_bytes: int = 20 * 1024 * 1024,
) -> None:
    """Connect the router to the shared SQLite store and file root."""
    global _store, _documents, _storage, _groups
    _store = store
    _documents = DocumentRepository(store) if store is not None else None
    _groups = GroupChatRepository(store) if store is not None else None
    if _documents is None:
        _storage = None
        return
    default_root = Path(__file__).resolve().parents[2] / "data" / "uploads"
    configured_root = root or os.getenv("FORUMMIND_STORAGE_ROOT") or default_root
    _storage = DocumentStorage(configured_root, _documents, max_upload_bytes=max_upload_bytes)


def _dependencies() -> tuple[DocumentRepository, DocumentStorage, GroupChatRepository]:
    if _documents is None or _storage is None or _groups is None:
        raise HTTPException(status_code=503, detail="document storage is unavailable")
    return _documents, _storage, _groups


def _require_group(
    group_chat_id: str,
    groups: GroupChatRepository,
    authorization: str | None = None,
    *,
    action: str = "read",
) -> None:
    if groups.get(group_chat_id) is None:
        raise HTTPException(status_code=404, detail="课题组不存在")
    if auth_required():
        decision = authorize_group_access(get_current_user(authorization), group_chat_id, action)
        if not decision.allowed:
            raise HTTPException(status_code=403, detail=decision.reason)


@router.post("/group-chats/{group_chat_id}/documents", response_model=DocumentRecord)
async def upload_document(
    group_chat_id: str,
    file: UploadFile = File(...),
    data_space: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    documents, storage, groups = _dependencies()
    _require_group(group_chat_id, groups, authorization, action="write")
    group = groups.get(group_chat_id)
    assert group is not None
    group_space = str(group["data_space"])
    if data_space is not None and data_space.strip() != group_space:
        raise HTTPException(status_code=422, detail="资料空间必须与当前课题组一致")
    if not file.filename:
        raise HTTPException(status_code=422, detail="filename is required")
    try:
        data = await file.read(storage.max_upload_bytes + 1)
        if len(data) > storage.max_upload_bytes:
            raise DocumentTooLargeError("document exceeds configured size limit")
        digest = hashlib.sha256(data).hexdigest()
        existing = documents.find_by_hash(group_chat_id, digest)
        if existing is not None:
            return JSONResponse(status_code=200, content=existing.model_dump(mode="json"))
        record = storage.save(
            group_chat_id,
            file.filename,
            data,
            group_space,
            file.content_type,
        )
    except DocumentTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except DocumentStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    append_chat_message(
        group_chat_id,
        sender_type="user",
        content=record.filename,
        kind="attachment",
        payload={
            "document_id": record.document_id,
            "filename": record.filename,
            "mime_type": record.mime_type,
            "size_bytes": record.size_bytes,
        },
        attachment_ids=[record.document_id],
    )
    return JSONResponse(status_code=201, content=record.model_dump(mode="json"))


@router.get("/group-chats/{group_chat_id}/documents", response_model=list[DocumentRecord])
def list_documents(group_chat_id: str, authorization: str | None = Header(default=None)) -> list[DocumentRecord]:
    documents, _storage, groups = _dependencies()
    _require_group(group_chat_id, groups, authorization)
    return documents.list_for_group(group_chat_id)


@router.post(
    "/group-chats/{group_chat_id}/documents/{document_id}/index",
    response_model=DocumentRecord,
)
def index_document(group_chat_id: str, document_id: str, authorization: str | None = Header(default=None)) -> DocumentRecord:
    """Parse and index one uploaded document, returning its durable state."""
    documents, storage, groups = _dependencies()
    _require_group(group_chat_id, groups, authorization, action="write")
    record = documents.get_for_group(document_id, group_chat_id)
    if record is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    append_chat_message(
        group_chat_id,
        sender_type="agent",
        sender_id="postdoc",
        content="资料正在处理",
        kind="run_status",
        payload={"document_id": record.document_id},
    )
    result = Indexer(documents, storage).process(record.document_id)
    if result.status == "ready":
        append_chat_message(
            group_chat_id,
            sender_type="agent",
            sender_id="postdoc",
            content="资料已可检索",
            kind="run_status",
            payload={"document_id": result.document_id},
        )
    else:
        append_chat_message(
            group_chat_id,
            sender_type="agent",
            sender_id="postdoc",
            content="资料处理失败，请检查文件内容后重试。",
            kind="run_status",
            payload={"document_id": result.document_id},
        )
    return result


@router.get("/documents/{document_id}", response_model=DocumentRecord)
def get_document(
    document_id: str,
    group_chat_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> DocumentRecord:
    documents, _storage, _groups = _dependencies()
    if auth_required() and group_chat_id is None:
        raise HTTPException(status_code=403, detail="group scope required")
    if group_chat_id is not None:
        _require_group(group_chat_id, _groups, authorization)
    record = (
        documents.get_for_group(document_id, group_chat_id)
        if group_chat_id is not None
        else documents.get(document_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return record


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: str,
    group_chat_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    documents, storage, _groups = _dependencies()
    if auth_required() and group_chat_id is None:
        raise HTTPException(status_code=403, detail="group scope required")
    if group_chat_id is not None:
        _require_group(group_chat_id, _groups, authorization)
    record = (
        documents.get_for_group(document_id, group_chat_id)
        if group_chat_id is not None
        else documents.get(document_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    path = storage.path_for(record)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文档文件不存在")
    return FileResponse(path, media_type=record.mime_type, filename=record.filename)
