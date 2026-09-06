from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_runtime.schemas import RuntimeEvent
from app.api import runs
from app.api.runtime_events import router
from app.orchestration.run_store import RunStore
from app.storage.sqlite_store import SQLiteStore


def test_events_api_replays_persisted_real_events_after_restart(tmp_path):
    database = SQLiteStore(tmp_path / "api-events.db")
    database.initialize()
    first = RunStore(database)
    state = first.create(
        "gc-a", "live", task_id="task-a",
        task_context={"task_id": "task-a", "data_space": "real", "document_ids": ["doc-a"]},
    )
    state.status = "completed"
    event = RuntimeEvent(
        event_id="event-a", cursor=1, session_id="session-a", invocation_id="inv-a",
        run_id=state.run_id, group_chat_id="gc-a", agent_id="agent-a",
        phase="independent_analysis", type="text_delta", payload={"content_delta": "真实候选"},
        data_space="real", timestamp=1.0, task_id="task-a", document_scope=["doc-a"],
    ).model_dump(mode="json")
    first.save_runtime_event(state, event)
    database.close()

    reopened = SQLiteStore(tmp_path / "api-events.db")
    reopened.initialize()
    previous = runs.run_store
    runs.run_store = RunStore(reopened)
    app = FastAPI()
    app.include_router(router)
    try:
        response = TestClient(app).get(f"/runs/{state.run_id}/events?after=0")
        assert response.status_code == 200
        assert "真实候选" in response.text
        assert "data_space\":\"real\"" in response.text
    finally:
        runs.run_store = previous
        reopened.close()
