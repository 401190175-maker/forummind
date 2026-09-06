"""HTTP contracts for document upload and real research task creation."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.documents import configure_persistence as configure_document_persistence
from app.api.documents import router as documents_router
from app.api.research_tasks import configure_persistence as configure_task_persistence
from app.api.research_tasks import router as tasks_router
from app.storage.repositories import GroupChatRepository
from app.storage.sqlite_store import SQLiteStore


def make_client(tmp_path, *, max_upload_bytes: int = 1024 * 1024) -> TestClient:
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    GroupChatRepository(store).save({
        "group_chat_id": "group-a",
        "data_space": "desensitized_real",
        "payload": {"group_chat": {"id": "group-a"}},
        "created_at": 1.0,
        "updated_at": 1.0,
    })
    configure_document_persistence(store, tmp_path / "files", max_upload_bytes=max_upload_bytes)
    configure_task_persistence(store)
    app = FastAPI()
    app.include_router(documents_router)
    app.include_router(tasks_router)
    return TestClient(app)


def test_upload_returns_metadata_and_download_does_not_use_user_filename(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/group-chats/group-a/documents",
        data={"data_space": "desensitized_real"},
        files={"file": ("../../secret.txt", b"density, strength\n", "text/plain")},
    )

    assert response.status_code == 201
    document = response.json()
    assert document["group_chat_id"] == "group-a"
    assert document["status"] == "uploaded"
    assert document["filename"] == "secret.txt"
    assert "secret.txt" not in document["storage_key"]

    downloaded = client.get(f"/documents/{document['document_id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"density, strength\n"


def test_upload_rejects_client_data_space_different_from_group(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/group-chats/group-a/documents",
        data={"data_space": "synthetic"},
        files={"file": ("evidence.txt", b"evidence", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "资料空间必须与当前课题组一致"


def test_upload_deduplicates_and_rejects_oversized_or_unsupported_files(tmp_path):
    client = make_client(tmp_path, max_upload_bytes=4)
    first = client.post(
        "/group-chats/group-a/documents",
        files={"file": ("a.txt", b"same", "text/plain")},
    )
    duplicate = client.post(
        "/group-chats/group-a/documents",
        files={"file": ("b.txt", b"same", "text/plain")},
    )
    oversized = client.post(
        "/group-chats/group-a/documents",
        files={"file": ("large.txt", b"large", "text/plain")},
    )
    unsupported = client.post(
        "/group-chats/group-a/documents",
        files={"file": ("run.exe", b"MZ", "application/x-msdownload")},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["document_id"] == first.json()["document_id"]
    assert oversized.status_code == 413
    assert unsupported.status_code == 415


def test_document_and_task_scope_cannot_cross_groups(tmp_path):
    client = make_client(tmp_path)
    uploaded = client.post(
        "/group-chats/group-a/documents",
        files={"file": ("a.md", b"claim", "text/markdown")},
    ).json()

    assert client.get(
        f"/documents/{uploaded['document_id']}?group_chat_id=group-b"
    ).status_code == 404
    task = client.post(
        "/group-chats/group-a/tasks",
        json={
            "title": "Real task",
            "question": "What does the document support?",
            "document_ids": [uploaded["document_id"]],
            "data_space": "desensitized_real",
        },
    )
    assert task.status_code == 201
    assert task.json()["document_ids"] == [uploaded["document_id"]]


def test_upload_and_task_require_an_existing_group(tmp_path):
    client = make_client(tmp_path)

    upload = client.post(
        "/group-chats/missing/documents",
        files={"file": ("a.txt", b"claim", "text/plain")},
    )
    task = client.post(
        "/group-chats/missing/tasks",
        json={"title": "Missing", "question": "Question"},
    )

    assert upload.status_code == 404
    assert task.status_code == 404


def test_uploaded_document_can_be_indexed_through_the_workbench_api(tmp_path):
    client = make_client(tmp_path)
    uploaded = client.post(
        "/group-chats/group-a/documents",
        files={"file": ("source.md", b"# Evidence\n\nStrength rises.", "text/markdown")},
    ).json()

    response = client.post(
        f"/group-chats/group-a/documents/{uploaded['document_id']}/index"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
