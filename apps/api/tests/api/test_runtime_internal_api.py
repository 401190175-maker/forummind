from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.runtime_internal import router
from app.orchestration.run_store import RunStore
from app.api import runtime_internal
from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def _client(monkeypatch, store: RunStore) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setenv("PI_RUNTIME_TOKEN", "secret")
    monkeypatch.setattr(runtime_internal, "run_store", store)
    return TestClient(app)


def test_runtime_tool_gateway_uses_server_run_identity(monkeypatch):
    store = RunStore()
    state = store.create("gc-1", "live", agent_specs=[{
        "agent_id": "agent-ms-1", "role": "master_student", "profile_version": "v1",
        "allowed_tools": ["memory.query"], "agent_instruction": {},
    }])
    client = _client(monkeypatch, store)
    response = client.post(
        "/internal/runtime/tool-calls",
        headers={"X-ForumMind-Runtime-Token": "secret"},
        json={
            "request_id": "req-1", "name": "memory.query", "arguments": {"query": "孔结构"},
            "run_id": state.run_id, "group_chat_id": "gc-1", "agent_id": "agent-ms-1",
            "role": "postdoc", "phase": "review_gate", "cycle": 1, "data_space": "synthetic",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_runtime_tool_gateway_requires_token_and_rejects_cross_run(monkeypatch):
    store = RunStore()
    store.create("gc-1", "live", agent_specs=[])
    client = _client(monkeypatch, store)
    body = {
        "request_id": "req-1", "name": "memory.query", "arguments": {},
        "run_id": "missing", "group_chat_id": "gc-1", "agent_id": "agent-ms-1",
        "data_space": "synthetic",
    }
    assert client.post("/internal/runtime/tool-calls", json=body).status_code == 401
    assert client.post(
        "/internal/runtime/tool-calls", headers={"X-ForumMind-Runtime-Token": "secret"}, json=body
    ).status_code == 404


def test_runtime_internal_route_is_hidden_from_openapi(monkeypatch):
    store = RunStore()
    client = _client(monkeypatch, store)
    assert "/internal/runtime/tool-calls" not in client.get("/openapi.json").json()["paths"]


def test_real_runtime_gateway_uses_persisted_task_scope(monkeypatch, tmp_path):
    database = SQLiteStore(tmp_path / "real-gateway.db")
    database.initialize()
    documents = DocumentRepository(database)
    documents.save(DocumentRecord(
        document_id="doc-a", group_chat_id="gc-1", filename="a.txt",
        mime_type="text/plain", size_bytes=3, sha256="a" * 64,
        storage_key="documents/doc-a.txt", data_space="desensitized_real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    documents.replace_chunks("doc-a", [DocumentChunk(
        document_id="doc-a", chunk_id="chunk-a", chunk_index=0,
        content="脱敏资料记录抗压强度。", page_or_location="page 1",
        char_start=0, char_end=10,
    )])
    documents.save_index_job(DocumentIndexJob(
        document_id="doc-a", status="ready", retry_count=0,
        started_at=1.0, finished_at=2.0, updated_at=2.0,
    ))
    ResearchTaskRepository(database, documents).create(ResearchTask(
        task_id="task-a", group_chat_id="gc-1", title="Strength", question="Question",
        document_ids=["doc-a"], data_space="desensitized_real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    store = RunStore()
    state = store.create(
        "gc-1", "live",
        task_context={
            "task_id": "task-a",
            "document_ids": ["doc-a"],
            "data_space": "desensitized_real",
        },
        agent_specs=[{
            "agent_id": "agent-ms-1", "role": "master_student", "profile_version": "v1",
            "allowed_tools": ["knowledge.search"], "agent_instruction": {},
        }],
    )
    monkeypatch.setattr(runtime_internal, "run_store", store)
    runtime_internal.configure_persistence(database)
    client = _client(monkeypatch, store)
    response = client.post(
        "/internal/runtime/tool-calls",
        headers={"X-ForumMind-Runtime-Token": "secret"},
        json={
            "request_id": "req-real", "name": "knowledge.search",
            "arguments": {
                "query": "抗压强度", "group_chat_id": "gc-other",
                "task_id": "task-other", "data_space": "synthetic",
            },
            "run_id": state.run_id, "group_chat_id": "gc-1", "agent_id": "agent-ms-1",
            "role": "postdoc", "phase": "review_gate", "cycle": 1,
            "data_space": "desensitized_real",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["payload"]["items"][0]["document_id"] == "doc-a"
