"""可恢复正式组会事件流服务测试。"""

import asyncio
import itertools
import threading
import time

import pytest

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentInvocation, AgentResult
import app.memory.timeline as memory_timeline
from app.meeting.service import MeetingService
from app.orchestration import engine
from app.orchestration.run_store import RunState, RunStep, RunStore
from app.scenario.loader import load_scenario
from app.storage.repositories import MeetingRepository
from app.storage.sqlite_store import SQLiteStore


@pytest.fixture(autouse=True)
def _isolate_memory_ids(monkeypatch):
    """Keep this module's live runs from changing another suite's fixture IDs."""
    monkeypatch.setattr(memory_timeline, "_seq", itertools.count(1))


def _valid_live_result(invocation: AgentInvocation) -> AgentResult:
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=f"真实输出：{invocation.agent_id}",
        structured_output={
            "statement": "判断",
            "boundary": "边界",
            "prediction": "预测",
            "falsification_condition": "可推翻条件",
        },
        data_space=invocation.data_space,
    )


def _live_state(store: RunStore) -> RunState:
    state = store.create(
        "gc-1",
        "live",
        runtime_name="pi",
        agent_specs=[
            {
                "agent_id": agent_id,
                "role": "master_student",
                "primary_ability": "独立科研分析",
            }
            for agent_id in ("agent-ms-1", "agent-ms-2", "agent-ms-3")
        ],
    )
    for index, agent_id in enumerate(("agent-ms-1", "agent-ms-2", "agent-ms-3"), 1):
        state.steps.append(
            RunStep(
                id=f"step-live-{index}",
                phase="independent_analysis",
                kind="claim",
                actor=agent_id,
                content=f"来自 {agent_id} 的真实汇报",
                payload={"source": "live", "runtime": "pi"},
                timestamp=float(index),
            )
        )
        state.persist_artifact(
            {
                "artifact_id": f"artifact:{state.run_id}:1:{agent_id}",
                "run_id": state.run_id,
                "group_chat_id": state.group_chat_id,
                "agent_id": agent_id,
                "artifact_type": "master_research_markdown",
                "filename": f"{agent_id}.md",
                "content": f"# {agent_id}\n\n来自 {agent_id} 的 Markdown 汇报",
                "data_space": "synthetic",
                "created_at": float(index),
                "updated_at": float(index),
            }
        )
    state.phase = "meeting"
    state.status = "awaiting_decision"
    state.persist()
    return state


def test_live_reports_pi_message_and_decision_are_ordered_events(tmp_path):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = _live_state(store)
    service = MeetingService(store, MeetingRepository(database))

    service.sync_live_reports(state)
    message = service.append_pi_message(state.run_id, "请补充孔结构的判别证据")
    service.apply_pi_decision(state.run_id, "approved", "保留最小判别实验")

    events = service.list_meeting_events(state.run_id)
    assert [event.actor_id for event in events] == [
        "agent-ms-1",
        "agent-ms-2",
        "agent-ms-3",
        "PI",
        "PI",
    ]
    assert [event.kind for event in events] == [
        "master_report",
        "master_report",
        "master_report",
        "message",
        "decision",
    ]
    assert message.source_refs == [f"pi:{message.id}"]
    assert [event.source for event in events] == ["live", "live", "live", "pi", "pi"]
    assert events[-1].source_refs
    assert events[-1].source_refs[0].startswith("step-")
    database.close()


def test_sync_live_reports_is_idempotent(tmp_path):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = _live_state(store)
    service = MeetingService(store, MeetingRepository(database))

    service.sync_live_reports(state)
    service.sync_live_reports(state)

    events = service.list_meeting_events(state.run_id)
    assert len(events) == 3
    assert len({event.id for event in events}) == 3
    database.close()


def test_replay_run_never_projects_live_claim_steps(tmp_path):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = store.create("gc-1", "replay")
    state.steps.append(
        RunStep(
            id="step-replay-live-shaped",
            phase="independent_analysis",
            kind="claim",
            actor="agent-ms-1",
            content="不应进入正式真实组会流",
            payload={"source": "live", "runtime": "pi"},
            timestamp=1.0,
        )
    )
    state.phase = "meeting"
    state.status = "awaiting_decision"
    state.persist()
    service = MeetingService(store, MeetingRepository(database))

    assert service.list_meeting_events(state.run_id) == []
    database.close()


def test_running_task_scoped_run_projects_completed_candidates_without_500(tmp_path):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = store.create(
        "gc-1",
        "live",
        task_id="task-1",
        agent_specs=[
            {"agent_id": agent_id, "role": "master_student"}
            for agent_id in ("agent-ms-1", "agent-ms-2", "agent-ms-3")
        ],
        task_context={"completion_mode": "candidate_review"},
    )
    state.steps.append(
        RunStep(
            id="step-candidate-1",
            phase="independent_analysis",
            kind="candidate",
            actor="agent-ms-1",
            content="部分候选结果",
            payload={"source": "live", "source_refs": ["chunk-1"]},
            timestamp=1.0,
        )
    )
    state.persist()
    service = MeetingService(store, MeetingRepository(database))

    events = service.list_meeting_events(state.run_id)

    assert [event.actor_id for event in events] == ["agent-ms-1"]
    assert [event.kind for event in events] == ["candidate_report"]
    database.close()


def test_live_engine_projects_three_real_reports_when_entering_meeting(tmp_path, monkeypatch):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = store.create(
        "gc-1",
        "live",
        runtime_name="pi",
        agent_specs=[
            {
                "agent_id": agent_id,
                "role": "master_student",
                "primary_ability": "独立科研分析",
            }
            for agent_id in ("agent-ms-1", "agent-ms-2", "agent-ms-3")
        ],
    )
    service = MeetingService(store, MeetingRepository(database))
    runtime = MockRuntime(result_factory=_valid_live_result)
    monkeypatch.setattr(engine, "create_runtime", lambda **_: runtime)

    asyncio.run(
        engine.run_live(
            load_scenario("foam_concrete_case"),
            state,
            meeting_service=service,
        )
    )

    events = service.list_meeting_events(state.run_id)
    assert state.status == "awaiting_decision"
    assert [event.kind for event in events] == ["master_report"] * 3
    assert [event.actor_id for event in events] == [
        "agent-ms-1",
        "agent-ms-2",
        "agent-ms-3",
    ]
    assert all(event.source_refs for event in events)
    database.close()


def test_events_survive_service_and_store_recreation(tmp_path):
    path = tmp_path / "forummind.db"
    first_database = SQLiteStore(path)
    first_database.initialize()
    first_store = RunStore(first_database)
    state = _live_state(first_store)
    first_service = MeetingService(first_store, MeetingRepository(first_database))
    first_service.sync_live_reports(state)
    first_service.append_pi_message(state.run_id, "重启后仍应看到这条插话")
    first_database.close()

    second_database = SQLiteStore(path)
    second_database.initialize()
    second_service = MeetingService(
        RunStore(second_database), MeetingRepository(second_database)
    )
    events = second_service.list_meeting_events(state.run_id)

    assert len(events) == 4
    assert events[-1].content == "重启后仍应看到这条插话"
    assert [event.source for event in events] == ["live", "live", "live", "pi"]
    assert [event.phase for event in events] == ["meeting"] * 4
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    second_database.close()


def test_recreated_service_backfills_missing_live_reports_and_failure(tmp_path):
    path = tmp_path / "forummind.db"
    first_database = SQLiteStore(path)
    first_database.initialize()
    first_store = RunStore(first_database)
    state = _live_state(first_store)
    state.status = "failed"
    state.phase = "failed"
    state.error = "agent-ms-2 failed"
    state.persist()
    first_database.close()

    second_database = SQLiteStore(path)
    second_database.initialize()
    second_store = RunStore(second_database)
    second_service = MeetingService(
        second_store, MeetingRepository(second_database)
    )

    events = second_service.list_meeting_events(state.run_id)

    assert [event.kind for event in events] == [
        "master_report",
        "master_report",
        "master_report",
        "failure",
    ]
    assert [event.actor_id for event in events[:3]] == [
        "agent-ms-1",
        "agent-ms-2",
        "agent-ms-3",
    ]
    assert events[-1].content == "agent-ms-2 failed"
    second_database.close()


def test_decision_and_event_roll_back_together_when_event_write_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "forummind.db"
    database = SQLiteStore(path)
    database.initialize()
    store = RunStore(database)
    state = _live_state(store)
    repository = MeetingRepository(database)
    service = MeetingService(store, repository)
    original_append = repository.append_event

    def fail_decision_event(event):
        if event["kind"] == "decision":
            raise RuntimeError("event storage unavailable")
        original_append(event)

    monkeypatch.setattr(repository, "append_event", fail_decision_event)

    with pytest.raises(RuntimeError, match="event storage unavailable"):
        service.apply_pi_decision(state.run_id, "approved", "允许")

    recovered = RunStore(database).get(state.run_id)
    assert recovered is not None
    assert recovered.status == "awaiting_decision"
    assert recovered.phase == "meeting"
    assert not any(step.kind == "decision" for step in recovered.steps)
    assert not any(
        event.kind == "decision"
        for event in service.list_meeting_events(state.run_id)
    )
    database.close()


def test_pi_decision_requires_awaiting_decision_and_rejects_repeat(tmp_path, monkeypatch):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = store.create("gc-1", "replay")
    service = MeetingService(store, MeetingRepository(database))

    with pytest.raises(ValueError, match="awaiting_decision"):
        service.apply_pi_decision(state.run_id, "approved", "太早")

    state.phase = "meeting"
    state.status = "awaiting_decision"
    state.persist()

    def fake_apply_decision(_scenario, current, option, reason):
        current.steps.append(
            RunStep(
                id="step-decision",
                phase="meeting",
                kind="decision",
                actor="PI",
                content=f"{option}: {reason}",
                payload={"option": option, "reason": reason},
                timestamp=4.0,
            )
        )
        current.status = "completed"
        current.phase = "discriminating_experiment"
        current.persist()

    monkeypatch.setattr("app.meeting.service.apply_decision", fake_apply_decision)
    service.apply_pi_decision(state.run_id, "approved", "允许")
    with pytest.raises(ValueError, match="awaiting_decision"):
        service.apply_pi_decision(state.run_id, "approved", "重复")
    database.close()


def test_concurrent_pi_decisions_only_apply_one_transition(tmp_path, monkeypatch):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = _live_state(store)
    service = MeetingService(store, MeetingRepository(database))
    entered = threading.Event()
    release = threading.Event()

    def fake_apply_decision(_scenario, current, option, reason):
        entered.set()
        assert release.wait(2)
        current.steps.append(
            RunStep(
                id="step-concurrent-decision",
                phase="meeting",
                kind="decision",
                actor="PI",
                content=f"{option}: {reason}",
                payload={"option": option, "reason": reason},
                timestamp=4.0,
            )
        )
        current.status = "completed"
        current.phase = "discriminating_experiment"
        current.persist()

    monkeypatch.setattr("app.meeting.service.apply_decision", fake_apply_decision)
    results: list[str] = []

    def invoke() -> None:
        try:
            service.apply_pi_decision(state.run_id, "approved", "允许")
        except ValueError:
            results.append("rejected")
        else:
            results.append("applied")

    first = threading.Thread(target=invoke)
    second = threading.Thread(target=invoke)
    first.start()
    assert entered.wait(2)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(2)
    second.join(2)

    assert sorted(results) == ["applied", "rejected"]
    assert len(
        [step for step in state.steps if step.kind == "decision"]
    ) == 1
    database.close()


def test_failure_event_preserves_error_without_scenario_success(tmp_path):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = store.create("gc-1", "live")
    state.status = "failed"
    state.phase = "failed"
    state.persist()
    service = MeetingService(store, MeetingRepository(database))

    event = service.append_failure(state, "Pi timeout for agent-ms-2")

    assert event.kind == "failure"
    assert event.actor_id == "system"
    assert event.content == "Pi timeout for agent-ms-2"
    assert service.list_meeting_events(state.run_id) == [event]
    database.close()
