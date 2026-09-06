"""Regression tests for the shared Gate C wiring owned by P2."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import runs, runtime_events
from app.domain.schemas import AgentProfile
from app.orchestration.run_store import RunState, RunStep, RunStore
from app.storage.repositories import MeetingRepository
from app.storage.sqlite_store import SQLiteStore
from app.meeting.service import MeetingService
from app.tasks.schemas import DatasetVersionRef, ResearchTask


def _profile(agent_id: str, role: str) -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        name=agent_id,
        role=role,
        primary_ability="资料分析",
        allowed_data_spaces=["desensitized_real"],
        allowed_tools=["knowledge.search"],
    )


def _spec(profile: AgentProfile) -> dict:
    return profile.model_dump(mode="json")


class _TaskRepository:
    def __init__(self, task: ResearchTask) -> None:
        self.task = task
        self.statuses: list[tuple[str, str]] = []

    def get_for_group(self, task_id: str, group_chat_id: str):
        if task_id == self.task.task_id and group_chat_id == self.task.group_chat_id:
            return self.task
        return None

    def set_status(self, task_id: str, status: str) -> None:
        self.statuses.append((task_id, status))


class _ImmediateThread:
    def __init__(self, *, target, daemon: bool) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


def test_task_api_dispatches_frozen_multi_agent_bridge(monkeypatch):
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-api-gate-c",
        group_chat_id="gc-api-gate-c",
        title="Gate C task",
        question="资料支持什么判断？",
        document_ids=[],
        dataset_refs=[DatasetVersionRef(dataset_id="dataset-a", version=1)],
        data_space="desensitized_real",
        status="ready",
        created_at=1.0,
        updated_at=1.0,
    )
    repository = _TaskRepository(task)
    run_store = RunStore(database)
    masters = [_profile(f"agent-ms-{index}", "master_student") for index in range(1, 4)]
    phd = _profile("agent-phd-1", "phd_student")
    postdoc = _profile("agent-postdoc-1", "postdoc")
    group_chat = SimpleNamespace(members=[])
    captured: dict[str, object] = {}

    async def fake_multi(task_value, agents, **kwargs):
        captured["task"] = task_value
        captured["agents"] = list(agents)
        captured.update(kwargs)
        state = kwargs["state"]
        state.status = "awaiting_review"
        state.phase = "awaiting_review"
        state.persist()
        return state

    monkeypatch.setattr(runs, "_store", database)
    monkeypatch.setattr(runs, "_task_repository", repository)
    monkeypatch.setattr(runs, "run_store", run_store)
    monkeypatch.setattr(runs, "get_created_group_chat", lambda _group_chat_id: group_chat)
    monkeypatch.setattr(runs, "_group_agent", lambda _group, _agent_id: masters[0])
    monkeypatch.setattr(
        runs,
        "_resolve_live_agent_specs",
        lambda _group, **_kwargs: [_spec(item) for item in masters],
    )
    monkeypatch.setattr(runs, "_resolve_review_agent_spec", lambda _group: _spec(phd))
    monkeypatch.setattr(
        runs,
        "_resolve_postdoc_agent_spec",
        lambda _group: _spec(postdoc),
        raising=False,
    )
    monkeypatch.setattr(runs, "run_live_task", lambda *_args, **_kwargs: pytest.fail("P1 path used"))
    monkeypatch.setattr(runs, "run_live_task_multi_agent", fake_multi, raising=False)
    monkeypatch.setattr(runs, "_project_terminal_run_message", lambda _state: None)
    monkeypatch.setattr(runs.threading, "Thread", _ImmediateThread)

    response = runs._start_task_live_run(
        task.group_chat_id,
        runs.RunRequest(mode="live", task_id=task.task_id, agent_id=masters[0].agent_id),
    )
    assert response["status"] == "awaiting_review"
    assert [agent.agent_id for agent in captured["agents"]] == [
        "agent-ms-1", "agent-ms-2", "agent-ms-3",
    ]
    assert captured["review_agent"].agent_id == "agent-phd-1"
    assert captured["postdoc_agent"].agent_id == "agent-postdoc-1"
    assert captured["meeting_service"] is runs._meeting_service
    assert captured["state"].task_context["allowed_dataset_refs"] == [
        {"dataset_id": "dataset-a", "version": 1}
    ]
    database.close()


def test_runtime_retry_dispatches_requested_agent(monkeypatch):
    store = RunStore()
    state = store.create(
        "gc-retry",
        "live",
        task_id="task-retry",
        agent_specs=[
            {"agent_id": f"agent-ms-{index}", "role": "master_student"}
            for index in range(1, 4)
        ],
        task_context={"task_id": "task-retry", "completion_mode": "candidate_review"},
    )
    state.status = "failed"
    state.phase = "independent_analysis"
    state.current_agent_id = "agent-ms-2"
    state.persist()
    previous_store = runs.run_store
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(runs, "run_store", store)
    def fake_retry(run_id: str, agent_id: str) -> None:
        calls.append((run_id, agent_id))
        state.status = "failed"
        state.control_state = "retry_requested"

    monkeypatch.setattr(runs, "retry_live_task_agent", fake_retry, raising=False)
    try:
        response = runtime_events.control_run(
            state.run_id,
            runtime_events.RuntimeControlRequest(action="retry", agent_id="agent-ms-2"),
        )
    finally:
        runs.run_store = previous_store

    assert calls == [(state.run_id, "agent-ms-2")]
    assert response["status"] == "failed"
    assert response["control_state"] == "retry_requested"


def test_retry_helper_reopens_task_before_reinvoking_frozen_agents(monkeypatch):
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-retry-helper",
        group_chat_id="gc-retry-helper",
        title="Retry helper task",
        question="重试失败的候选分析",
        document_ids=[],
        data_space="desensitized_real",
        status="failed",
        created_at=1.0,
        updated_at=1.0,
    )
    repository = _TaskRepository(task)
    store = RunStore(database)
    masters = [_profile(f"agent-ms-{index}", "master_student") for index in range(1, 4)]
    state = store.create(
        task.group_chat_id,
        "live",
        task_id=task.task_id,
        agent_specs=[_spec(item) for item in masters],
        task_context={
            "task_id": task.task_id,
            "completion_mode": "candidate_review",
            "data_space": task.data_space,
            "document_ids": [],
        },
    )
    state.status = "failed"
    state.current_agent_id = "agent-ms-2"
    state.agent_attempts["agent-ms-2"] = 1
    state.steps.append(RunStep(
        id="failed-agent-ms-2",
        phase="independent_analysis",
        kind="invocation",
        actor="agent-ms-2",
        content="temporary provider failure",
        payload={
            "status": "error",
            "invocation_id": "inv-agent-ms-2-1",
            "attempt": 1,
        },
        timestamp=1.0,
    ))
    state.persist()
    captured: dict[str, object] = {}

    async def fake_multi(_task, agents, **kwargs):
        captured["agents"] = list(agents)
        captured.update(kwargs)
        state.status = "awaiting_review"
        state.persist()
        return state

    monkeypatch.setattr(runs, "run_store", store)
    monkeypatch.setattr(runs, "_store", database)
    monkeypatch.setattr(runs, "_task_repository", repository)
    monkeypatch.setattr(runs, "run_live_task_multi_agent", fake_multi)
    monkeypatch.setattr(runs, "_project_terminal_run_message", lambda _state: None)
    monkeypatch.setattr(runs.threading, "Thread", _ImmediateThread)

    try:
        retried = runs.retry_live_task_agent(state.run_id, "agent-ms-2")
    finally:
        database.close()

    assert retried.status == "awaiting_review"
    assert [agent.agent_id for agent in captured["agents"]] == [
        "agent-ms-1", "agent-ms-2", "agent-ms-3",
    ]
    assert repository.statuses == [
        ("task-retry-helper", "running"),
        ("task-retry-helper", "awaiting_review"),
    ]


def test_retry_helper_rejects_a_nonfailed_p2_run(monkeypatch):
    store = RunStore()
    state = store.create(
        "gc-retry-state",
        "live",
        task_id="task-retry-state",
        agent_specs=[
            {"agent_id": f"agent-ms-{index}", "role": "master_student"}
            for index in range(1, 4)
        ],
        task_context={"task_id": "task-retry-state", "completion_mode": "candidate_review"},
    )
    state.status = "awaiting_review"
    state.persist()
    monkeypatch.setattr(runs, "run_store", store)

    with pytest.raises(ValueError, match="failed"):
        runs.retry_live_task_agent(state.run_id, "agent-ms-1")


def test_retry_helper_rejects_agent_without_failed_invocation(monkeypatch):
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-retry-target",
        group_chat_id="gc-retry-target",
        title="Retry target task",
        question="只允许重试失败 Agent",
        document_ids=[],
        data_space="desensitized_real",
        status="failed",
        created_at=1.0,
        updated_at=1.0,
    )
    repository = _TaskRepository(task)
    store = RunStore(database)
    state = store.create(
        task.group_chat_id,
        "live",
        task_id=task.task_id,
        agent_specs=[
            _spec(_profile(f"agent-ms-{index}", "master_student"))
            for index in range(1, 4)
        ],
        task_context={
            "task_id": task.task_id,
            "completion_mode": "candidate_review",
            "data_space": task.data_space,
        },
    )
    state.status = "failed"
    state.persist()
    monkeypatch.setattr(runs, "run_store", store)
    monkeypatch.setattr(runs, "_store", database)
    monkeypatch.setattr(runs, "_task_repository", repository)

    try:
        with pytest.raises(ValueError, match="失败 invocation"):
            runs.retry_live_task_agent(state.run_id, "agent-ms-1")
    finally:
        database.close()


def test_retry_helper_rejects_agent_when_latest_invocation_succeeded(monkeypatch):
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-retry-latest",
        group_chat_id="gc-retry-latest",
        title="Latest invocation task",
        question="只允许重试最近一次失败 invocation",
        document_ids=[],
        data_space="desensitized_real",
        status="failed",
        created_at=1.0,
        updated_at=1.0,
    )
    repository = _TaskRepository(task)
    store = RunStore(database)
    state = store.create(
        task.group_chat_id,
        "live",
        task_id=task.task_id,
        agent_specs=[
            _spec(_profile(f"agent-ms-{index}", "master_student"))
            for index in range(1, 4)
        ],
        task_context={
            "task_id": task.task_id,
            "completion_mode": "candidate_review",
            "data_space": task.data_space,
        },
    )
    state.status = "failed"
    state.agent_attempts["agent-ms-1"] = 1
    state.steps.extend([
        RunStep(
            id="failed-agent-ms-1",
            phase="independent_analysis",
            kind="invocation",
            actor="agent-ms-1",
            content="temporary provider failure",
            payload={"status": "error", "invocation_id": "inv-ms-1-1", "attempt": 1},
            timestamp=1.0,
        ),
        RunStep(
            id="succeeded-agent-ms-1",
            phase="independent_analysis",
            kind="invocation",
            actor="agent-ms-1",
            content="completed",
            payload={"status": "ok", "invocation_id": "inv-ms-1-2", "attempt": 2},
            timestamp=2.0,
        ),
    ])
    state.persist()
    monkeypatch.setattr(runs, "run_store", store)
    monkeypatch.setattr(runs, "_store", database)
    monkeypatch.setattr(runs, "_task_repository", repository)

    try:
        with pytest.raises(ValueError, match="最近一次失败 invocation"):
            runs.retry_live_task_agent(state.run_id, "agent-ms-1")
    finally:
        database.close()


def test_retry_helper_rejects_agent_at_attempt_cap(monkeypatch):
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-retry-cap",
        group_chat_id="gc-retry-cap",
        title="Retry cap task",
        question="达到重试上限",
        document_ids=[],
        data_space="desensitized_real",
        status="failed",
        created_at=1.0,
        updated_at=1.0,
    )
    repository = _TaskRepository(task)
    store = RunStore(database)
    state = store.create(
        task.group_chat_id,
        "live",
        task_id=task.task_id,
        agent_specs=[
            _spec(_profile(f"agent-ms-{index}", "master_student"))
            for index in range(1, 4)
        ],
        task_context={
            "task_id": task.task_id,
            "completion_mode": "candidate_review",
            "data_space": task.data_space,
        },
    )
    state.status = "failed"
    state.agent_attempts["agent-ms-1"] = 2
    state.steps.append(RunStep(
        id="failed-cap",
        phase="independent_analysis",
        kind="invocation",
        actor="agent-ms-1",
        content="failed",
        payload={"status": "error"},
        timestamp=1.0,
    ))
    state.persist()
    monkeypatch.setattr(runs, "run_store", store)
    monkeypatch.setattr(runs, "_store", database)
    monkeypatch.setattr(runs, "_task_repository", repository)

    try:
        with pytest.raises(ValueError, match="最大重试次数"):
            runs.retry_live_task_agent(state.run_id, "agent-ms-1")
    finally:
        database.close()


def _task_scoped_state(store: RunStore) -> RunState:
    state = store.create(
        "gc-meeting-gate-c",
        "live",
        task_id="task-meeting-gate-c",
        agent_specs=[
            {"agent_id": f"agent-ms-{index}", "role": "master_student"}
            for index in range(1, 4)
        ],
        review_agent_spec={"agent_id": "agent-phd-1", "role": "phd_student"},
        postdoc_agent_spec={"agent_id": "agent-postdoc-1", "role": "postdoc"},
        task_context={
            "task_id": "task-meeting-gate-c",
            "completion_mode": "candidate_review",
            "data_space": "desensitized_real",
        },
    )
    state.status = "awaiting_review"
    state.phase = "awaiting_review"
    for index in range(1, 4):
        state.steps.append(RunStep(
            id=f"candidate-{index}", phase="independent_analysis", kind="candidate",
            actor=f"agent-ms-{index}", content=f"candidate {index}",
            payload={"source": "live", "candidate_id": f"candidate-{index}"}, timestamp=float(index),
        ))
    for index, kind in enumerate(("counterexample", "falsification_condition", "missing_observation"), start=1):
        state.steps.append(RunStep(
            id=f"review-{index}", phase="review_gate", kind="review_opinion",
            actor="agent-phd-1", content=kind, payload={"source": "live", "kind": kind},
            timestamp=3.0 + index,
        ))
    state.steps.extend([
        RunStep(
            id="postdoc-request", phase="postdoc_exchange", kind="request",
            actor="agent-postdoc-1", content="request", payload={"source": "live"}, timestamp=7.0,
        ),
        RunStep(
            id="postdoc-synthesis", phase="postdoc_exchange", kind="synthesis",
            actor="agent-postdoc-1", content="synthesis", payload={"source": "live"}, timestamp=8.0,
        ),
        RunStep(
            id="suggestion", phase="postdoc_exchange", kind="suggested_decision",
            actor="system", content="pending PI", payload={"source": "live", "source_refs": ["postdoc-synthesis"]},
            timestamp=9.0,
        ),
    ])
    state.persist()
    return state


def test_meeting_service_projects_task_scoped_materials():
    database = SQLiteStore(":memory:")
    database.initialize()
    store = RunStore(database)
    state = _task_scoped_state(store)
    service = MeetingService(store, MeetingRepository(database))

    events = service.list_meeting_events(state.run_id)

    assert [event.kind for event in events] == [
        "candidate_report", "candidate_report", "candidate_report",
        "review_gate", "review_gate", "review_gate",
        "postdoc_request", "postdoc_response", "suggested_decision",
    ]
    assert not any(event.kind == "decision" for event in events)
    database.close()
