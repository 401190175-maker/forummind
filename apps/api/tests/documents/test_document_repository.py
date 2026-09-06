"""Repository contracts for real research documents."""

import pytest

from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentRecord
from app.documents.storage import DocumentStorage
from app.storage.sqlite_store import SQLiteStore


def document_for(group_chat_id: str, *, document_id: str = "doc-1", sha256: str = "a" * 64) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        group_chat_id=group_chat_id,
        filename="results.txt",
        mime_type="text/plain",
        size_bytes=3,
        sha256=sha256,
        storage_key=f"documents/{document_id}.txt",
        data_space="desensitized_real",
        status="uploaded",
        created_at=1.0,
        updated_at=1.0,
    )


def test_document_repository_persists_metadata_and_group_scope(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    repository = DocumentRepository(store)
    repository.save(document_for("group-a"))

    stored = repository.get_for_group("doc-1", "group-a")
    assert stored is not None
    assert stored.filename == "results.txt"
    assert stored.sha256 == "a" * 64
    assert repository.get_for_group("doc-1", "group-b") is None


def test_document_storage_deduplicates_by_hash_only_inside_group(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    repository = DocumentRepository(store)
    storage = DocumentStorage(tmp_path / "files", repository)

    first = storage.save("group-a", "first.txt", b"abc", "desensitized_real")
    duplicate = storage.save("group-a", "renamed.txt", b"abc", "desensitized_real")
    other_group = storage.save("group-b", "renamed.txt", b"abc", "desensitized_real")

    assert duplicate.document_id == first.document_id
    assert other_group.document_id != first.document_id
    assert len([path for path in (tmp_path / "files").rglob("*") if path.is_file()]) == 2


def test_task_document_association_rolls_back_when_document_is_out_of_scope(tmp_path):
    from app.tasks.repository import ResearchTaskRepository
    from app.tasks.schemas import ResearchTask

    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    documents = DocumentRepository(store)
    documents.save(document_for("group-a"))
    tasks = ResearchTaskRepository(store, documents)

    task = ResearchTask(
        task_id="task-1",
        group_chat_id="group-a",
        title="Compression study",
        question="How does density affect strength?",
        document_ids=["doc-1", "missing"],
        data_space="desensitized_real",
        status="ready",
        created_at=1.0,
        updated_at=1.0,
    )
    with pytest.raises(ValueError, match="document"):
        tasks.create(task)

    assert tasks.get_for_group("task-1", "group-a") is None
