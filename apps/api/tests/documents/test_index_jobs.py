"""Persistent document indexing state machine contracts."""

from app.documents.indexer import Indexer
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentRecord
from app.documents.storage import DocumentStorage
from app.storage.sqlite_store import SQLiteStore


def test_indexer_transitions_uploaded_to_ready_and_persists_chunks(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    documents = DocumentRepository(store)
    storage = DocumentStorage(tmp_path / "files", documents)
    document = storage.save("group-a", "results.txt", b"density=500\nstrength=8", "desensitized_real")
    indexer = Indexer(documents, storage)

    indexed = indexer.process(document.document_id)
    recovered = documents.get(document.document_id)
    chunks = documents.list_chunks(document.document_id)
    job = documents.get_index_job(document.document_id)

    assert indexed.status == "ready"
    assert recovered is not None and recovered.status == "ready"
    assert chunks and "density=500" in chunks[0].content
    assert job is not None
    assert job.status == "ready"
    assert job.error_code == ""
    assert job.retry_count == 0
    assert job.started_at is not None and job.finished_at is not None


def test_indexer_is_idempotent_and_recovers_processing_documents(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    documents = DocumentRepository(store)
    storage = DocumentStorage(tmp_path / "files", documents)
    document = storage.save("group-a", "results.md", b"# Result\n\nconfirmed", "desensitized_real")
    indexer = Indexer(documents, storage)
    indexer.process(document.document_id)
    first_chunks = documents.list_chunks(document.document_id)
    indexer.process(document.document_id)
    second_chunks = documents.list_chunks(document.document_id)

    assert [chunk.chunk_id for chunk in first_chunks] == [chunk.chunk_id for chunk in second_chunks]

    documents.set_status(document.document_id, "processing")
    indexer.recover_processing()
    assert documents.get(document.document_id).status == "uploaded"


def test_indexer_marks_malformed_document_failed_with_retry_metadata(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.initialize()
    documents = DocumentRepository(store)
    storage = DocumentStorage(tmp_path / "files", documents)
    record = DocumentRecord(
        document_id="doc-bad", group_chat_id="group-a", filename="bad.pdf",
        mime_type="application/pdf", size_bytes=3, sha256="b" * 64,
        storage_key="documents/bad.pdf", data_space="desensitized_real",
        status="uploaded", created_at=1.0, updated_at=1.0,
    )
    bad_path = storage.path_for(record)
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_bytes(b"bad")
    documents.save(record)

    result = Indexer(documents, storage).process("doc-bad")
    job = documents.get_index_job("doc-bad")

    assert result.status == "failed"
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "document_processing"
    assert job.retry_count == 0
    assert job.finished_at is not None

    Indexer(documents, storage).process("doc-bad")
    assert documents.get_index_job("doc-bad").retry_count == 1
