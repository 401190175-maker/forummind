import pytest

from app.agent_runtime.schemas import AgentResult
from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.orchestration.run_store import RunStore
from app.research.candidate_service import CandidateService
from app.research.contracts import CandidateClaim
from app.research.validators import ResultValidationError
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def _service(tmp_path):
    store = SQLiteStore(tmp_path / "candidate.db")
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
    return store, CandidateService(store), state.run_id


def _candidate(refs=None, run_id="run-a", **overrides):
    values = {
        "candidate_id": "candidate-a", "task_id": "task-a", "run_id": run_id,
        "agent_id": "agent-a", "claim": "强度随密度增加而增加。",
        "evidence_refs": ["chunk-a"] if refs is None else refs,
        "reasoning_summary": "资料中有对应趋势。", "uncertainty": "样本有限。",
        "next_action": "补充样本。", "data_space": "real", "status": "candidate",
    }
    values.update(overrides)
    return CandidateClaim(**values)


def test_candidate_with_fake_reference_is_rejected(tmp_path):
    store, service, run_id = _service(tmp_path)
    with pytest.raises(ResultValidationError, match="evidence_ref"):
        service.create(_candidate(["chunk-does-not-exist"], run_id=run_id))
    store.close()


def test_candidate_validation_rejects_wrong_identity_and_space(tmp_path):
    store, service, run_id = _service(tmp_path)
    with pytest.raises(ResultValidationError, match="data_space"):
        service.create(_candidate(data_space="desensitized_real", run_id=run_id))
    with pytest.raises(ResultValidationError, match="agent_id"):
        service.create(_candidate(agent_id="foreign-agent", run_id=run_id))
    store.close()


def test_agent_result_can_be_converted_to_candidate_after_contract_validation(tmp_path):
    store, service, run_id = _service(tmp_path)
    result = AgentResult(
        agent_id="agent-a", status="ok", content="候选",
        structured_output={
            "claim": "强度随密度增加而增加。", "evidence_refs": ["chunk-a"],
            "reasoning_summary": "资料中有对应趋势。", "uncertainty": "样本有限。",
            "next_action": "补充样本。",
        }, data_space="real",
    )
    candidate = service.from_agent_result(
        result, task_id="task-a", run_id=run_id, agent_id="agent-a"
    )
    assert candidate.status == "candidate"
    assert candidate.evidence_refs == ["chunk-a"]
    loaded = service.get(candidate.candidate_id)
    assert loaded is not None
    assert loaded.evidence[0].document_id == "doc-a"
    store.close()
