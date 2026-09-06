from app.agent_runtime.schemas import RuntimeEvent
from app.agent_runtime.event_bridge import project_runtime_event
from app.orchestration.run_store import RunStore
from app.storage.repositories import RuntimeEventRepository
from app.storage.sqlite_store import SQLiteStore


def runtime_event(run_id="run-1", cursor=7):
    return RuntimeEvent(
        event_id=f"event-{cursor}", cursor=cursor, session_id="s-1", invocation_id="i-1",
        run_id=run_id, group_chat_id="gc-1", agent_id="a-1", phase="independent_analysis",
        type="text_delta", payload={"content_delta": "x"}, data_space="synthetic", timestamp=1.0,
    ).model_dump(mode="json")


def test_event_replay_is_idempotent_after_api_restart(tmp_path):
    store = SQLiteStore(tmp_path / "events.db")
    store.initialize()
    repository = RuntimeEventRepository(store)
    repository.append(runtime_event())
    repository.append(runtime_event())
    assert len(repository.list_for_run("run-1", after=6)) == 1
    store.close()


def test_run_state_reloads_cursor_and_events_from_snapshot(tmp_path):
    database = SQLiteStore(tmp_path / "runs.db")
    database.initialize()
    store = RunStore(database)
    state = store.create("gc-1", "live")
    store.save_runtime_event(state, runtime_event(state.run_id, 2))
    recovered = RunStore(database).get(state.run_id)
    assert recovered is not None
    assert recovered.runtime_cursor == 2
    assert recovered.runtime_events[0]["event_id"] == "event-2"
    database.close()


def test_run_event_cursor_is_monotonic_across_native_sessions(tmp_path):
    database = SQLiteStore(tmp_path / "multi-session-events.db")
    database.initialize()
    store = RunStore(database)
    state = store.create("gc-1", "live")

    first = runtime_event(state.run_id, 1)
    first.update(event_id="event-session-1", session_id="session-1", invocation_id="inv-1")
    second = runtime_event(state.run_id, 1)
    second.update(event_id="event-session-2", session_id="session-2", invocation_id="inv-2")

    store.save_runtime_event(state, first)
    store.save_runtime_event(state, second)

    recovered_events = store.list_runtime_events(state.run_id, after=1)

    assert [event["session_id"] for event in recovered_events] == ["session-2"]
    assert [event["cursor"] for event in recovered_events] == [2]
    assert state.runtime_cursor == 2
    database.close()


def test_projected_runtime_events_persist_with_run_level_cursors(tmp_path):
    database = SQLiteStore(tmp_path / "projected-events.db")
    database.initialize()
    store = RunStore(database)
    state = store.create("gc-1", "live")

    first = runtime_event(state.run_id, 1)
    first.update(event_id="event-project-1", session_id="session-1", invocation_id="inv-1")
    second = runtime_event(state.run_id, 2)
    second.update(event_id="event-project-2", session_id="session-1", invocation_id="inv-1")

    for value in (first, second):
        project_runtime_event(state, value)
        store.save_runtime_event(state, value)

    recovered = RunStore(database).resume_run(state.run_id)

    assert recovered is not None
    assert [event["cursor"] for event in recovered.runtime_events] == [1, 2]
    assert [event["event_id"] for event in store.list_runtime_events(state.run_id)] == [
        "event-project-1", "event-project-2"
    ]
    assert recovered.runtime_cursor == 2
    database.close()
