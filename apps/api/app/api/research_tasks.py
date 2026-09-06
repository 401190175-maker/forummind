"""HTTP API for durable research tasks."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.documents.repository import DocumentRepository
from app.storage.repositories import GroupChatRepository
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask, ResearchTaskCreateRequest


router = APIRouter(tags=["research-tasks"])
_tasks: ResearchTaskRepository | None = None
_groups: GroupChatRepository | None = None


def configure_persistence(store: SQLiteStore | None) -> None:
    global _tasks, _groups
    if store is None:
        _tasks = None
        _groups = None
        return
    _groups = GroupChatRepository(store)
    _tasks = ResearchTaskRepository(store, DocumentRepository(store))


def _dependencies() -> tuple[ResearchTaskRepository, GroupChatRepository]:
    if _tasks is None or _groups is None:
        raise HTTPException(status_code=503, detail="research task storage is unavailable")
    return _tasks, _groups


def _require_group(group_chat_id: str, groups: GroupChatRepository) -> None:
    if groups.get(group_chat_id) is None:
        raise HTTPException(status_code=404, detail="课题组不存在")


@router.post("/group-chats/{group_chat_id}/tasks", response_model=ResearchTask, status_code=201)
def create_research_task(
    group_chat_id: str,
    body: ResearchTaskCreateRequest,
) -> ResearchTask:
    tasks, groups = _dependencies()
    _require_group(group_chat_id, groups)
    group = groups.get(group_chat_id)
    assert group is not None
    now = time.time()
    task = ResearchTask(
        task_id=f"task-{uuid4().hex}",
        group_chat_id=group_chat_id,
        title=body.title,
        question=body.question,
        document_ids=body.document_ids,
        dataset_refs=body.dataset_refs,
        data_space=(body.data_space or str(group["data_space"])),
        status="ready",
        created_at=now,
        updated_at=now,
    )
    try:
        return tasks.create(task)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/group-chats/{group_chat_id}/tasks", response_model=list[ResearchTask])
def list_research_tasks(group_chat_id: str) -> list[ResearchTask]:
    tasks, groups = _dependencies()
    _require_group(group_chat_id, groups)
    return tasks.list_for_group(group_chat_id)
