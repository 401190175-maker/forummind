"""Durable chat projections for Live research interactions."""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import group_chats as group_chats_api
from app.api import documents as documents_api
from app.group_chats import creation_service, messages
from app.group_chats.creation_service import create_group_chat
from app.group_chats.schemas import CreateGroupChatRequest, MemberSelection, RoleMemberSelection, SelectionMode
from app.meeting.scheduler import MeetingScheduleRequest, schedule_service
from app.storage.repositories import GroupChatRepository
from app.storage.sqlite_store import SQLiteStore


def _real_request() -> CreateGroupChatRequest:
    return CreateGroupChatRequest(
        topic_name="真实资料分析",
        topic_summary="基于上传资料分析抗压强度变化",
        member_selection=MemberSelection(
            postdoc=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=1),
            phd_student=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=1),
            master_student=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=3),
        ),
    )


def test_new_group_persists_a_postdoc_welcome_without_internal_metadata(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "welcome.db")
    store.initialize()
    previous_group_store = creation_service._persistence_store
    previous_message_store = messages._persistence_store
    creation_service.configure_persistence(store)
    messages.configure_persistence(store)
    try:
        group = create_group_chat(_real_request())
        timeline = messages.list_messages(group.group_chat.id)
    finally:
        messages.reset_messages()
        messages.configure_persistence(previous_message_store)
        creation_service._created_group_chats.clear()
        creation_service.configure_persistence(previous_group_store)
        store.close()

    welcome = timeline[0]
    assert welcome.sender_type == "agent"
    assert welcome.kind == "text"
    assert "data_space" not in welcome.content
    assert "SQLite" not in welcome.content


def test_indexing_document_projects_attachment_and_postdoc_statuses(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "documents.db")
    store.initialize()
    GroupChatRepository(store).save(
        {
            "group_chat_id": "group-a",
            "data_space": "desensitized_real",
            "payload": {"group_chat": {"id": "group-a"}},
            "created_at": 1.0,
            "updated_at": 1.0,
        }
    )
    previous_message_store = messages._persistence_store
    previous_document_dependencies = (
        documents_api._store,
        documents_api._documents,
        documents_api._storage,
        documents_api._groups,
    )
    messages.configure_persistence(store)
    documents_api.configure_persistence(store, tmp_path / "files")
    app = FastAPI()
    app.include_router(documents_api.router)
    client = TestClient(app)
    try:
        upload = client.post(
            "/group-chats/group-a/documents",
            files={"file": ("evidence.txt", b"strength evidence", "text/plain")},
        )
        assert upload.status_code == 201
        document_id = upload.json()["document_id"]
        indexed = client.post(f"/group-chats/group-a/documents/{document_id}/index")
        assert indexed.status_code == 200
        timeline = messages.list_messages("group-a")
    finally:
        messages.reset_messages()
        messages.configure_persistence(previous_message_store)
        (
            documents_api._store,
            documents_api._documents,
            documents_api._storage,
            documents_api._groups,
        ) = previous_document_dependencies
        store.close()

    assert [item.kind for item in timeline[-3:]] == ["attachment", "run_status", "run_status"]
    assert all(item.data_space.value == "desensitized_real" for item in timeline[-3:])
    assert timeline[-1].payload["document_id"] == document_id


def test_failed_document_index_projects_a_safe_postdoc_status(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "failed-documents.db")
    store.initialize()
    GroupChatRepository(store).save(
        {
            "group_chat_id": "group-a",
            "data_space": "desensitized_real",
            "payload": {"group_chat": {"id": "group-a"}},
            "created_at": 1.0,
            "updated_at": 1.0,
        }
    )
    previous_message_store = messages._persistence_store
    previous_document_dependencies = (
        documents_api._store,
        documents_api._documents,
        documents_api._storage,
        documents_api._groups,
    )
    messages.configure_persistence(store)
    documents_api.configure_persistence(store, tmp_path / "files")
    app = FastAPI()
    app.include_router(documents_api.router)
    client = TestClient(app)
    try:
        uploaded = client.post(
            "/group-chats/group-a/documents",
            files={"file": ("broken.pdf", b"not a PDF", "application/pdf")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["document_id"]
        indexed = client.post(f"/group-chats/group-a/documents/{document_id}/index")
        assert indexed.status_code == 200
        assert indexed.json()["status"] == "failed"
        projection = messages.list_messages("group-a")[-1]
    finally:
        messages.reset_messages()
        messages.configure_persistence(previous_message_store)
        (
            documents_api._store,
            documents_api._documents,
            documents_api._storage,
            documents_api._groups,
        ) = previous_document_dependencies
        store.close()

    assert projection.kind == "run_status"
    assert projection.content == "资料处理失败，请检查文件内容后重试。"
    assert "PDF" not in projection.content
    assert projection.payload == {"document_id": document_id}


def test_saving_meeting_projects_a_postdoc_message(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "meeting.db")
    store.initialize()
    previous_group_store = creation_service._persistence_store
    previous_message_store = messages._persistence_store
    creation_service.configure_persistence(store)
    messages.configure_persistence(store)
    try:
        group = create_group_chat(_real_request())
        scheduled = group_chats_api.save_meeting_schedule_route(
            group.group_chat.id,
            MeetingScheduleRequest(
                next_meeting_at=datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
            ),
        )
        timeline = messages.list_messages(group.group_chat.id)
    finally:
        schedule_service.delete_for_group(group.group_chat.id)
        messages.reset_messages()
        messages.configure_persistence(previous_message_store)
        creation_service._created_group_chats.clear()
        creation_service.configure_persistence(previous_group_store)
        store.close()

    projection = timeline[-1]
    assert projection.sender_type == "agent"
    assert projection.sender_id == "postdoc"
    assert projection.kind == "meeting_schedule"
    assert projection.payload == {"next_meeting_at": scheduled.next_meeting_at.isoformat()}
