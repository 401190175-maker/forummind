"""Repository contracts for durable research tasks."""

from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentRecord
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def test_research_task_persists_document_associations_and_is_group_scoped(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    documents = DocumentRepository(store)
    documents.save(DocumentRecord(
        document_id="doc-a", group_chat_id="group-a", filename="a.md",
        mime_type="text/markdown", size_bytes=1, sha256="a" * 64,
        storage_key="documents/a.md", data_space="real", status="uploaded",
        created_at=1.0, updated_at=1.0,
    ))
    tasks = ResearchTaskRepository(store, documents)
    tasks.create(ResearchTask(
        task_id="task-a", group_chat_id="group-a", title="Task A",
        question="Question A", document_ids=["doc-a"], data_space="real",
        status="ready", created_at=1.0, updated_at=1.0,
    ))

    stored = tasks.get_for_group("task-a", "group-a")
    assert stored is not None
    assert stored.document_ids == ["doc-a"]
    assert tasks.get_for_group("task-a", "group-b") is None
    assert tasks.list_for_group("group-a")[0].title == "Task A"
