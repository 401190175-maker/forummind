"""Live Runs started from confirmed chat clarifications."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import service as agents_service
from app.api import runs
from app.agent_runtime.schemas import RuntimeSelection
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.domain.schemas import AgentProfile, AgentRole, DataSpace
from app.group_chats.messages import ClarificationClosedError
from app.group_chats.schemas import FormalTaskContext, MentionTarget
from app.orchestration.run_store import RunStore
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


class _NoOpThread:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def start(self) -> None:
        pass


def _ready_context() -> FormalTaskContext:
    return FormalTaskContext(
        clarification_id="clarification-ready",
        group_chat_id="group-live",
        initial_intent="比较孔结构变化与抗压强度的证据",
        topic_name="泡沫混凝土强度",
        topic_summary="基于课题组资料分析强度变化",
        mention=MentionTarget(target_type="member", target_id="member-1", label="资料分析员"),
        clarifier_agent_id="agent-clarifier",
        confirmed_at=1.0,
        data_space=DataSpace.DESENSITIZED_REAL,
    )


def _ready_document(store: SQLiteStore) -> str:
    document_id = "doc-ready"
    documents = DocumentRepository(store)
    documents.save(
        DocumentRecord(
            document_id=document_id,
            group_chat_id="group-live",
            filename="evidence.txt",
            mime_type="text/plain",
            size_bytes=16,
            sha256="a" * 64,
            storage_key="group-live/evidence.txt",
            data_space="desensitized_real",
            status="ready",
            created_at=1.0,
            updated_at=1.0,
        )
    )
    documents.save_index_job(
        DocumentIndexJob(
            document_id=document_id,
            status="ready",
            retry_count=0,
            started_at=1.0,
            finished_at=2.0,
            updated_at=2.0,
        )
    )
    return document_id


def _group() -> SimpleNamespace:
    return SimpleNamespace(
        group_chat=SimpleNamespace(data_space=DataSpace.DESENSITIZED_REAL),
        topic=SimpleNamespace(topic_name="泡沫混凝土强度", topic_summary="资料分析"),
        members=[
            SimpleNamespace(
                id="member-1",
                status="active",
                agent_profile_ref=SimpleNamespace(object_id="agent:agent-clarifier"),
            )
        ],
    )


def _agent_record() -> dict:
    profile = AgentProfile(
        agent_id="agent-clarifier",
        name="资料分析员",
        role=AgentRole.PHD_STUDENT,
        primary_ability="资料分析",
        allowed_data_spaces=[DataSpace.DESENSITIZED_REAL],
        allowed_tools=["knowledge.search"],
    )
    return {
        "agent_id": profile.agent_id,
        "enabled": True,
        "profile": profile.model_dump(mode="json"),
    }


def test_confirmed_clarification_creates_scoped_live_task_and_run(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "live-run.db")
    store.initialize()
    document_id = _ready_document(store)
    previous_store = runs._store
    previous_run_store = runs.run_store
    runs.configure_persistence(store)
    runs.run_store = RunStore()
    monkeypatch.setattr(runs.threading, "Thread", _NoOpThread)
    monkeypatch.setattr(runs, "get_created_group_chat", lambda _group_id: _group())
    monkeypatch.setattr(runs, "create_formal_task", lambda *_args: _ready_context())
    monkeypatch.setattr(agents_service, "get_agent_record", lambda _agent_id: _agent_record())
    monkeypatch.setattr(
        runs,
        "_resolve_selection",
        lambda _mode: RuntimeSelection(api_mode="live", resolved_mode="live", runtime_name="pi"),
    )
    app = FastAPI()
    app.include_router(runs.router)
    client = TestClient(app)
    try:
        response = client.post(
            "/group-chats/group-live/runs",
            json={"mode": "live", "clarification_id": "clarification-ready"},
        )
        assert response.status_code == 200
        state = runs.run_store.get(response.json()["run_id"])
        assert state is not None
        assert state.mode == "live"
        assert state.task_id
        assert [event["type"] for event in state.runtime_events] == ["run_started"]
        started = state.runtime_events[0]
        assert started["cursor"] == 1
        assert started["task_id"] == state.task_id
        assert started["document_scope"] == [document_id]
        assert started["agent_id"] == "agent-clarifier"
        task = ResearchTaskRepository(store).get_for_group(state.task_id, "group-live")
        assert task is not None
        assert task.source_clarification_id == "clarification-ready"
        assert task.document_ids == [document_id]
        assert state.agent_specs[0]["agent_id"] == "agent-clarifier"
    finally:
        runs.run_store = previous_run_store
        runs.configure_persistence(previous_store)
        store.close()


def test_repeated_clarification_start_returns_the_existing_run(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "idempotent-live-run.db")
    store.initialize()
    _ready_document(store)
    previous_store = runs._store
    previous_run_store = runs.run_store
    runs.configure_persistence(store)
    runs.run_store = RunStore()
    monkeypatch.setattr(runs.threading, "Thread", _NoOpThread)
    monkeypatch.setattr(runs, "get_created_group_chat", lambda _group_id: _group())
    monkeypatch.setattr(runs, "create_formal_task", lambda *_args: _ready_context())
    monkeypatch.setattr(agents_service, "get_agent_record", lambda _agent_id: _agent_record())
    monkeypatch.setattr(
        runs,
        "_resolve_selection",
        lambda _mode: RuntimeSelection(api_mode="live", resolved_mode="live", runtime_name="pi"),
    )
    app = FastAPI()
    app.include_router(runs.router)
    client = TestClient(app)
    try:
        first = client.post(
            "/group-chats/group-live/runs",
            json={"mode": "live", "clarification_id": "clarification-ready"},
        )
        second = client.post(
            "/group-chats/group-live/runs",
            json={"mode": "live", "clarification_id": "clarification-ready"},
        )

        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert len(runs.run_store._runs) == 1
    finally:
        runs.run_store = previous_run_store
        runs.configure_persistence(previous_store)
        store.close()


def test_unready_clarification_returns_actionable_conflict(monkeypatch) -> None:
    monkeypatch.setattr(runs, "get_created_group_chat", lambda _group_id: _group())
    monkeypatch.setattr(
        runs,
        "create_formal_task",
        lambda *_args: (_ for _ in ()).throw(ClarificationClosedError("澄清尚未完成")),
    )
    app = FastAPI()
    app.include_router(runs.router)
    client = TestClient(app)

    response = client.post(
        "/group-chats/group-live/runs",
        json={"mode": "live", "clarification_id": "clarification-blocked"},
    )

    assert response.status_code == 409
    assert "请先" in response.json()["detail"]


def test_terminal_live_run_projects_a_safe_candidate_message(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "terminal-run.db")
    store.initialize()
    task = ResearchTask(
        task_id="task-candidate",
        group_chat_id="group-live",
        title="候选结论",
        question="整理强度证据",
        source_clarification_id="clarification-ready",
        document_ids=[],
        data_space="desensitized_real",
        status="running",
        created_at=1.0,
        updated_at=1.0,
    )
    ResearchTaskRepository(store).create(task)
    previous_store = runs._store
    previous_run_store = runs.run_store
    runs.configure_persistence(store)
    runs.run_store = RunStore()
    state = runs.run_store.create(
        "group-live", "live", task_id=task.task_id, task_context={"candidate_id": "candidate-1"}
    )
    state.status = "awaiting_review"
    projected: list[dict] = []

    monkeypatch.setattr(runs, "append_chat_message", lambda *_args, **kwargs: projected.append(kwargs))
    monkeypatch.setattr(runs, "_clarification_reply_message_id", lambda *_args: "user-message-1")
    try:
        runs._project_terminal_run_message(state)
        assert projected == [
            {
                "sender_type": "agent",
                "sender_id": "postdoc",
                "content": "已生成候选结果，等待你审阅。",
                "kind": "candidate",
                "payload": {
                    "run_id": state.run_id,
                    "status": "awaiting_review",
                    "candidate_id": "candidate-1",
                },
                "reply_to_message_id": "user-message-1",
            }
        ]
    finally:
        runs.run_store = previous_run_store
        runs.configure_persistence(previous_store)
        store.close()


def test_failed_live_run_projects_actionable_safe_status(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "failed-run.db")
    store.initialize()
    task = ResearchTask(
        task_id="task-failed",
        group_chat_id="group-live",
        title="失败分析",
        question="整理强度证据",
        source_clarification_id="clarification-ready",
        document_ids=[],
        data_space="desensitized_real",
        status="running",
        created_at=1.0,
        updated_at=1.0,
    )
    ResearchTaskRepository(store).create(task)
    previous_store = runs._store
    previous_run_store = runs.run_store
    runs.configure_persistence(store)
    runs.run_store = RunStore()
    state = runs.run_store.create("group-live", "live", task_id=task.task_id)
    state.status = "failed"
    state.error = "provider token rejected"
    projected: list[dict] = []

    monkeypatch.setattr(runs, "append_chat_message", lambda *_args, **kwargs: projected.append(kwargs))
    monkeypatch.setattr(runs, "_clarification_reply_message_id", lambda *_args: "user-message-1")
    try:
        runs._project_terminal_run_message(state)
        assert projected == [
            {
                "sender_type": "agent",
                "sender_id": "postdoc",
                "content": "分析未能完成，请检查资料和成员配置后重试。",
                "kind": "run_status",
                "payload": {"run_id": state.run_id, "status": "failed"},
                "reply_to_message_id": "user-message-1",
            }
        ]
        assert "provider" not in projected[0]["content"]
    finally:
        runs.run_store = previous_run_store
        runs.configure_persistence(previous_store)
        store.close()
