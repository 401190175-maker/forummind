from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.orchestration.run_store import RunStore
from app.research.candidate_service import CandidateService
from app.research.contracts import CandidateClaim
from app.storage.sqlite_store import SQLiteStore
import pytest
from app.research.candidate_service import ApprovalConflictError
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def _service(tmp_path):
    store = SQLiteStore(tmp_path / "approval.db")
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
    candidate = CandidateClaim(
        candidate_id="candidate-a", task_id="task-a", run_id=state.run_id,
        agent_id="agent-a", claim="强度随密度增加而增加。", evidence_refs=["chunk-a"],
        reasoning_summary="资料中有对应趋势。", uncertainty="样本有限。",
        next_action="补充样本。", data_space="real", status="candidate",
    )
    service = CandidateService(store)
    service.create(candidate)
    return store, service, candidate


def test_approval_is_idempotent_and_creates_one_formal_projection(tmp_path):
    store, service, candidate = _service(tmp_path)
    first = service.approve(candidate.candidate_id, "user-1")
    second = service.approve(candidate.candidate_id, "user-1")

    assert first.status == "approved"
    assert second.status == "approved"
    assert service.count_formal_claims(candidate.candidate_id) == 1
    assert service.count_approvals(candidate.candidate_id) == 1
    assert service.formal_evidence_status(candidate.candidate_id) == "pending"
    store.close()


def test_rejection_is_idempotent_and_never_projects_formal_claim(tmp_path):
    store, service, candidate = _service(tmp_path)
    first = service.reject(candidate.candidate_id, "user-1", "引用不足")
    second = service.reject(candidate.candidate_id, "user-1", "重复请求")

    assert first.status == "rejected"
    assert second.status == "rejected"
    assert service.count_formal_claims(candidate.candidate_id) == 0
    assert service.count_approvals(candidate.candidate_id) == 1
    store.close()


def test_approval_after_rejection_is_a_conflict(tmp_path):
    store, service, candidate = _service(tmp_path)
    service.reject(candidate.candidate_id, "user-1", "引用不足")

    with pytest.raises(ApprovalConflictError, match="rejected"):
        service.approve(candidate.candidate_id, "user-1")
    assert service.last_error == "approval_conflict"
    store.close()
