"""Read-only tool adapter contracts for real document search."""

from app.agent_runtime.schemas import AgentInvocation
from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.search import KnowledgeSearch
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask
from app.tools.context import build_tool_execution_context
from app.tools.knowledge import register_knowledge_tool
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest


def _real_registry(tmp_path, *, max_result_bytes: int = 8192):
    store = SQLiteStore(tmp_path / "tool.db")
    store.initialize()
    documents = DocumentRepository(store)
    documents.save(DocumentRecord(
        document_id="doc-a", group_chat_id="group-a", filename="a.txt",
        mime_type="text/plain", size_bytes=8, sha256="a" * 64,
        storage_key="documents/doc-a.txt", data_space="desensitized_real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    documents.replace_chunks("doc-a", [DocumentChunk(
        document_id="doc-a", chunk_id="chunk-a", chunk_index=0,
        content="脱敏资料记录抗压强度为 3.2 MPa。", page_or_location="page 1",
        char_start=0, char_end=20,
    )])
    documents.save_index_job(DocumentIndexJob(
        document_id="doc-a", status="ready", retry_count=0,
        started_at=1.0, finished_at=2.0, updated_at=2.0,
    ))
    ResearchTaskRepository(store, documents).create(ResearchTask(
        task_id="task-a", group_chat_id="group-a", title="Strength", question="Question",
        document_ids=["doc-a"], data_space="desensitized_real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    invocation = AgentInvocation(
        run_id="run-a", group_chat_id="group-a", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student",
        task="search", allowed_tools=["knowledge.search"], data_space="desensitized_real",
        context={"task_id": "task-a", "allowed_document_ids": ["doc-a"]},
    )
    context = build_tool_execution_context(
        invocation, runtime_name="pi",
        limits={"max_calls": 3, "max_items": 10, "max_result_bytes": max_result_bytes, "deadline_seconds": 30},
    )
    registry = ToolRegistry()
    register_knowledge_tool(registry, KnowledgeSearch(KnowledgeRepository(store)))
    return registry, context


def test_knowledge_tool_uses_trusted_scope_and_ignores_identity_arguments(tmp_path):
    registry, context = _real_registry(tmp_path)

    result = registry.execute(ToolRequest(
        request_id="request-1", name="knowledge.search", data_space="desensitized_real",
        arguments={
            "query": "抗压强度",
            "group_chat_id": "group-other",
            "task_id": "task-other",
            "data_space": "synthetic",
        },
    ), context)

    assert result.status == "ok"
    assert result.data_space == "desensitized_real"
    assert [item["document_id"] for item in result.payload["items"]] == ["doc-a"]
    assert result.source_refs == ["chunk-a"]


def test_knowledge_tool_rejects_document_scope_expansion(tmp_path):
    registry, context = _real_registry(tmp_path)

    result = registry.execute(ToolRequest(
        request_id="request-2", name="knowledge.search", data_space="desensitized_real",
        arguments={"query": "抗压强度", "document_ids": ["doc-foreign"]},
    ), context)

    assert result.status == "error"
    assert result.error_code == "document_scope_denied"


def test_knowledge_tool_result_is_limited_by_registry_budget(tmp_path):
    registry, context = _real_registry(tmp_path, max_result_bytes=20)

    result = registry.execute(ToolRequest(
        request_id="request-3", name="knowledge.search", data_space="desensitized_real",
        arguments={"query": "抗压强度"},
    ), context)

    assert result.status == "limit_exceeded"
    assert result.error_code == "result_size_exceeded"
