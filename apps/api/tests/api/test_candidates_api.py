from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import candidates, runs
from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.orchestration.run_store import RunStore
from app.research.candidate_service import CandidateService
from app.research.contracts import CandidateClaim
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def _client(tmp_path):
    store = SQLiteStore(tmp_path / "candidate-api.db")
    store.initialize()
    documents = DocumentRepository(store)
    documents.save(DocumentRecord(
        document_id="doc-a", group_chat_id="gc-a", filename="source.txt",
        mime_type="text/plain", size_bytes=10, sha256="a" * 64,
        storage_key="documents/a.txt", data_space="real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    documents.replace_chunks("doc-a", [DocumentChunk(
        document_id="doc-a", chunk_id="chunk-a", chunk_index=0,
        content="强度结果", page_or_location="page 1", char_start=0, char_end=4,
    )])
    documents.save_index_job(DocumentIndexJob(
        document_id="doc-a", status="ready", retry_count=0,
        started_at=1.0, finished_at=2.0, updated_at=2.0,
    ))
    ResearchTaskRepository(store).create(ResearchTask(
        task_id="task-a", group_chat_id="gc-a", title="任务", question="问题",
        document_ids=["doc-a"], data_space="real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    state = RunStore(store).create(
        "gc-a", "live", task_id="task-a",
        agent_specs=[{"agent_id": "agent-a", "role": "master_student"}],
    )
    service = CandidateService(store)
    service.create(CandidateClaim(
        candidate_id="candidate-a", task_id="task-a", run_id=state.run_id,
        agent_id="agent-a", claim="强度随密度增加而增加。", evidence_refs=["chunk-a"],
        reasoning_summary="资料中有对应趋势。", uncertainty="样本有限。",
        next_action="补充样本。", data_space="real", status="candidate",
    ))
    candidates.configure_persistence(store)
    previous = runs.run_store
    runs.run_store = RunStore(store)
    app = FastAPI()
    app.include_router(candidates.router)
    return store, state.run_id, TestClient(app), previous


def test_candidates_api_lists_and_approves_candidate(tmp_path):
    store, run_id, client, previous = _client(tmp_path)
    try:
        runs.run_store.get(run_id).status = "awaiting_review"
        listed = client.get(f"/runs/{run_id}/candidates")
        assert listed.status_code == 200
        assert listed.json()[0]["status"] == "candidate"
        assert listed.json()[0]["evidence"][0]["chunk_id"] == "chunk-a"
        assert listed.json()[0]["evidence"][0]["page_or_location"] == "page 1"

        response = client.post(
            f"/runs/{run_id}/candidates/candidate-a/approve",
            json={"actor_id": "user-1"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        assert runs.run_store.get(run_id).status == "completed"
    finally:
        runs.run_store = previous
        store.close()


def test_candidates_api_requires_review_gate_before_approval(tmp_path):
    store, run_id, client, previous = _client(tmp_path)
    try:
        response = client.post(
            f"/runs/{run_id}/candidates/candidate-a/approve",
            json={"actor_id": "user-1"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "approval_conflict"
    finally:
        runs.run_store = previous
        store.close()
