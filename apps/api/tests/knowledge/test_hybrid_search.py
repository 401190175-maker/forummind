"""Behavioral contracts for task-scoped hybrid knowledge retrieval."""

import importlib.util

import pytest

from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.knowledge.embeddings import EmbeddingIndex
from app.knowledge.hybrid_search import HybridSearch
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import SearchHit, SearchScope
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def test_hybrid_search_module_exposes_the_p3_retrieval_boundary():
    module = importlib.util.find_spec("app.knowledge.hybrid_search")

    assert module is not None


class _TopicEmbedder:
    dimensions = 2

    def embed(self, text: str) -> tuple[float, float]:
        return (1.0, 0.0) if any(term in text for term in ("轻质材料", "泡沫")) else (0.0, 1.0)


def _seed(tmp_path):
    store = SQLiteStore(tmp_path / "hybrid.db")
    store.initialize()
    documents = DocumentRepository(store)
    tasks = ResearchTaskRepository(store, documents)
    for document_id, content in (
        ("doc-a", "泡沫混凝土的密度和孔结构决定轻质材料的隔热表现。"),
        ("doc-b", "轻质材料的抗压强度需要结合养护条件判断。"),
    ):
        documents.save(DocumentRecord(
            document_id=document_id, group_chat_id="group-a", filename=f"{document_id}.txt",
            mime_type="text/plain", size_bytes=len(content.encode()), sha256=(document_id + "0" * 64)[:64],
            storage_key=f"documents/{document_id}.txt", data_space="desensitized_real", status="ready",
            created_at=1.0, updated_at=1.0,
        ))
        documents.replace_chunks(document_id, [DocumentChunk(
            document_id=document_id, chunk_id=f"chunk-{document_id}", chunk_index=0,
            content=content, page_or_location="page:1", char_start=0, char_end=len(content),
        )])
        documents.save_index_job(DocumentIndexJob(
            document_id=document_id, status="ready", retry_count=0,
            started_at=1.0, finished_at=2.0, updated_at=2.0,
        ))
    tasks.create(ResearchTask(
        task_id="task-a", group_chat_id="group-a", title="Materials", question="Question",
        document_ids=["doc-a", "doc-b"], data_space="desensitized_real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    return store, documents


def _scope() -> SearchScope:
    return SearchScope(
        group_chat_id="group-a", task_id="task-a", data_space="desensitized_real",
        allowed_document_ids=["doc-a", "doc-b"],
    )


def test_hybrid_search_merges_lexical_and_semantic_hits_with_provenance(tmp_path):
    store, _documents = _seed(tmp_path)
    search = HybridSearch(
        KnowledgeRepository(store),
        embedding_index=EmbeddingIndex(),
        embedder=_TopicEmbedder(),
    )

    hits = search.search(_scope(), "轻质材料", 5)

    assert {hit.chunk_id for hit in hits} == {"chunk-doc-a", "chunk-doc-b"}
    assert hits[0].source_ref.startswith("document:")
    assert hits[0].data_space == "desensitized_real"
    assert hits[0].verification_status == "pending"
    assert hits[0].source_mode == "live"
    assert hits[0].page_or_location == "page:1"


def test_hybrid_search_rebuilds_stale_vector_entries_from_durable_chunks(tmp_path):
    store, documents = _seed(tmp_path)
    index = EmbeddingIndex()
    index.upsert("doc-a", "chunk-stale", (1.0, 0.0))
    documents.replace_chunks("doc-a", [DocumentChunk(
        document_id="doc-a", chunk_id="chunk-fresh", chunk_index=0,
        content="泡沫材料的新测量记录。", page_or_location="page:2", char_start=0, char_end=12,
    )])
    search = HybridSearch(KnowledgeRepository(store), embedding_index=index, embedder=_TopicEmbedder())

    hits = search.search(_scope(), "轻质材料", 5)

    assert "chunk-stale" not in {hit.chunk_id for hit in hits}
    assert "chunk-fresh" in {hit.chunk_id for hit in hits}


def test_search_hit_rejects_fixture_provenance_in_a_real_data_space():
    with pytest.raises(ValueError, match="fixture provenance"):
        SearchHit(
            document_id="doc-1", chunk_id="chunk-1", content="content",
            page_or_location="page:1", char_start=0, char_end=7, score=1.0,
            source_ref="document:doc-1#chunk:chunk-1", data_space="real",
            verification_status="fixture", source_mode="fixture",
        )
