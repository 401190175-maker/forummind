"""Search contracts for the real, group-scoped knowledge index."""

from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import SearchScope
from app.knowledge.search import KnowledgeSearch
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def _document(group_chat_id: str, document_id: str, *, data_space: str = "real", status: str = "ready") -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        group_chat_id=group_chat_id,
        filename=f"{document_id}.txt",
        mime_type="text/plain",
        size_bytes=10,
        sha256=(document_id.replace("-", "") + "0" * 64)[:64],
        storage_key=f"documents/{document_id}.txt",
        data_space=data_space,
        status=status,
        created_at=1.0,
        updated_at=1.0,
    )


def _seed(tmp_path):
    store = SQLiteStore(tmp_path / "knowledge.db")
    store.initialize()
    documents = DocumentRepository(store)
    tasks = ResearchTaskRepository(store, documents)
    documents.save(_document("group-a", "doc-a"))
    documents.save(_document("group-a", "doc-b"))
    documents.save(_document("group-b", "doc-foreign"))
    documents.replace_chunks("doc-a", [
        DocumentChunk(
            document_id="doc-a", chunk_id="chunk-a-1", chunk_index=0,
            content="抗压强度随密度提高而提高，试样 A 的抗压强度为 3.2 MPa。",
            page_or_location="page 1", char_start=0, char_end=30,
        ),
        DocumentChunk(
            document_id="doc-a", chunk_id="chunk-a-2", chunk_index=1,
            content="孔结构观察记录了气泡尺寸和连通性。",
            page_or_location="page 2", char_start=31, char_end=50,
        ),
    ])
    documents.replace_chunks("doc-b", [
        DocumentChunk(
            document_id="doc-b", chunk_id="chunk-b-1", chunk_index=0,
            content="抗压强度的补充测量来自未授权文档 B。",
            page_or_location="page 1", char_start=0, char_end=20,
        ),
    ])
    documents.replace_chunks("doc-foreign", [
        DocumentChunk(
            document_id="doc-foreign", chunk_id="chunk-foreign-1", chunk_index=0,
            content="抗压强度来自另一个课题组。",
            page_or_location="page 1", char_start=0, char_end=15,
        ),
    ])
    for document_id in ("doc-a", "doc-b", "doc-foreign"):
        documents.save_index_job(DocumentIndexJob(
            document_id=document_id, status="ready", retry_count=0,
            started_at=1.0, finished_at=2.0, updated_at=2.0,
        ))
    tasks.create(ResearchTask(
        task_id="task-a", group_chat_id="group-a", title="Strength", question="Question",
        document_ids=["doc-a"], data_space="real", status="ready", created_at=1.0, updated_at=1.0,
    ))
    tasks.create(ResearchTask(
        task_id="task-b", group_chat_id="group-a", title="Other", question="Question",
        document_ids=["doc-b"], data_space="real", status="ready", created_at=1.0, updated_at=1.0,
    ))
    return KnowledgeSearch(KnowledgeRepository(store))


def _scope(*document_ids: str, group_chat_id: str = "group-a", task_id: str = "task-a", data_space: str = "real") -> SearchScope:
    return SearchScope(
        group_chat_id=group_chat_id,
        task_id=task_id,
        data_space=data_space,
        allowed_document_ids=list(document_ids),
    )


def test_search_ranks_matching_chunks_and_returns_source_locations(tmp_path):
    search = _seed(tmp_path)

    hits = search.search(_scope("doc-a"), "抗压强度", 5)

    assert hits[0].chunk_id == "chunk-a-1"
    assert hits[0].document_id == "doc-a"
    assert hits[0].page_or_location == "page 1"
    assert hits[0].char_start == 0
    assert hits[0].char_end == 30
    assert isinstance(hits[0].score, float)


def test_search_never_returns_unassigned_or_cross_group_documents(tmp_path):
    search = _seed(tmp_path)

    hits = search.search(_scope("doc-a", "doc-b", "doc-foreign"), "抗压强度", 5)

    assert [hit.document_id for hit in hits] == ["doc-a"]


def test_search_returns_empty_for_non_matching_query_and_honors_limit(tmp_path):
    search = _seed(tmp_path)

    assert search.search(_scope("doc-a"), "不存在的术语", 5) == []
    assert len(search.search(_scope("doc-a"), "抗压强度 OR 孔结构", 1)) == 1


def test_lexical_search_falls_back_to_partial_term_matches(tmp_path):
    search = _seed(tmp_path)

    rows = search.repository.search_rows(_scope("doc-a"), "无关术语 抗压强度", 5)

    assert [row["chunk_id"] for row in rows] == ["chunk-a-1"]
