import pytest

from app.agent_runtime.schemas import RuntimeEvent, RuntimeSessionRef
from app.orchestration.run_store import RunStore
from app.storage.repositories import RunRepository, RuntimeEventRepository
from app.storage.sqlite_store import SQLiteStore


def _event(run_id: str, cursor: int, event_id: str | None = None) -> dict:
    return RuntimeEvent(
        event_id=event_id or f"event-{cursor}", cursor=cursor, session_id="session-a",
        invocation_id="invocation-a", run_id=run_id, group_chat_id="gc-a",
        agent_id="agent-a", phase="independent_analysis", type="text_delta",
        payload={"content_delta": "候选"}, data_space="desensitized_real", timestamp=float(cursor),
        task_id="task-a", document_scope=["doc-a"],
    ).model_dump(mode="json")


def test_runtime_event_append_once_is_idempotent_and_cursor_is_monotonic(tmp_path):
    store = SQLiteStore(tmp_path / "events.db")
    store.initialize()
    events = RuntimeEventRepository(store)
    run_id = "run-a"

    assert events.append_once(_event(run_id, 12)) is True
    assert events.append_once(_event(run_id, 12, "duplicate-id")) is False
    assert events.save_cursor(run_id, 12) == 12
    assert events.save_cursor(run_id, 7) == 12
    assert events.get_cursor(run_id) == 12
    assert len(events.list_for_run(run_id, after=0)) == 1
    store.close()


def test_runtime_event_cursor_is_run_global_after_server_start(tmp_path):
    database = SQLiteStore(tmp_path / "run-global-cursor.db")
    database.initialize()
    runs = RunStore(database)
    state = runs.create("gc-a", "live", task_id="task-a")
    started = {
        "event_id": f"run-started:{state.run_id}",
        "cursor": 0,
        "session_id": f"server:{state.run_id}",
        "invocation_id": f"run-started:{state.run_id}",
        "run_id": state.run_id,
        "group_chat_id": state.group_chat_id,
        "agent_id": "agent-a",
        "phase": "independent_analysis",
        "type": "run_started",
        "payload": {"status": "running"},
        "data_space": "desensitized_real",
        "task_id": "task-a",
        "document_scope": ["doc-a"],
        "timestamp": 1.0,
    }
    native = _event(state.run_id, 1, "native-event")

    first = runs.prepare_runtime_event(state, started)
    runs.save_runtime_event(state, first)
    second = runs.prepare_runtime_event(state, native)
    runs.save_runtime_event(state, second)

    assert first["cursor"] == 1
    assert second["cursor"] == 2
    assert native["cursor"] == 1
    assert [event["cursor"] for event in runs.list_runtime_events(state.run_id)] == [1, 2]
    database.close()


def test_run_repository_cursor_is_monotonic(tmp_path):
    store = SQLiteStore(tmp_path / "run-cursor.db")
    store.initialize()
    repository = RunRepository(store)

    assert repository.save_cursor("run-a", 12) == 12
    assert repository.save_cursor("run-a", 7) == 12
    assert repository.get_cursor("run-a") == 12
    store.close()


def test_run_restart_hydrates_session_task_cursor_and_events(tmp_path):
    database = SQLiteStore(tmp_path / "recovery.db")
    database.initialize()
    runs = RunStore(database)
    state = runs.create(
        "gc-a", "live", task_id="task-a",
        task_context={"task_id": "task-a", "data_space": "desensitized_real", "document_ids": ["doc-a"]},
    )
    state.session_refs["agent-a"] = RuntimeSessionRef(
        session_id="session-a", group_chat_id="gc-a", run_id=state.run_id,
        agent_id="agent-a", phase="independent_analysis", data_space="desensitized_real",
        last_cursor=12,
    )
    state.persist()
    runs.save_runtime_event(state, _event(state.run_id, 12))
    database.close()

    reopened = SQLiteStore(tmp_path / "recovery.db")
    reopened.initialize()
    recovered = RunStore(reopened).resume_run(state.run_id)

    assert recovered is not None
    assert recovered.task_id == "task-a"
    assert recovered.runtime_cursor == 12
    assert recovered.session_refs["agent-a"].session_id == "session-a"
    assert recovered.runtime_events[0]["task_id"] == "task-a"
    reopened.close()


def test_runtime_session_cursor_is_monotonic_across_repeated_saves(tmp_path):
    database = SQLiteStore(tmp_path / "session-cursor.db")
    database.initialize()
    runs = RunStore(database)
    state = runs.create("gc-a", "live", task_id="task-a")
    ref = RuntimeSessionRef(
        session_id="session-a", group_chat_id="gc-a", run_id=state.run_id,
        agent_id="agent-a", phase="independent_analysis",
        data_space="desensitized_real", task_id="task-a", last_cursor=12,
    )

    runs.save_runtime_session(ref)
    runs.save_runtime_session(ref.model_copy(update={"last_cursor": 7, "document_scope": ["doc-a"]}))
    with pytest.raises(ValueError, match="session identity"):
        runs.save_runtime_session(ref.model_copy(update={"run_id": "run-other"}))
    database.close()

    reopened = SQLiteStore(tmp_path / "session-cursor.db")
    reopened.initialize()
    recovered = RunStore(reopened).resume_run(state.run_id)

    assert recovered is not None
    assert recovered.session_refs["agent-a"].last_cursor == 12
    assert recovered.session_refs["agent-a"].document_scope == ["doc-a"]
    reopened.close()
