import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_runtime.schemas import RuntimeEvent
from app.api import runs
from app.api.runtime_events import router
from app.orchestration.run_store import RunStore


def test_control_rejects_missing_run():
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).post("/runs/run-1/control", json={"action": "abort"}).status_code == 404


def test_runtime_sse_replays_events_and_settled_marker():
    app = FastAPI()
    app.include_router(router)
    previous = runs.run_store
    store = RunStore()
    runs.run_store = store
    try:
        state = store.create("gc-1", "live")
        state.status = "completed"
        state.runtime_events.append(RuntimeEvent(
            event_id="e-1", cursor=1, session_id="s-1", invocation_id="i-1", run_id=state.run_id,
            group_chat_id="gc-1", agent_id="a-1", phase="independent_analysis", type="text_delta",
            payload={"content_delta": "candidate"}, timestamp=1.0,
        ).model_dump(mode="json"))
        response = TestClient(app).get(f"/runs/{state.run_id}/events?after=0")
        assert response.status_code == 200
        assert "runtime.text_delta" in response.text
        assert "runtime.settled" in response.text
    finally:
        runs.run_store = previous


def test_runtime_sse_follows_events_appended_after_initial_replay():
    previous = runs.run_store
    store = RunStore()
    runs.run_store = store
    try:
        state = store.create("gc-1", "live")
        state.runtime_events.append(RuntimeEvent(
            event_id="e-1", cursor=1, session_id="s-1", invocation_id="i-1", run_id=state.run_id,
            group_chat_id="gc-1", agent_id="a-1", phase="independent_analysis", type="text_delta",
            payload={"content_delta": "first"}, timestamp=1.0,
        ).model_dump(mode="json"))
        response = router.routes[-2].endpoint(state.run_id, after=0)
        async def consume():
            assert "first" in await response.body_iterator.__anext__()
            state.runtime_events.append(RuntimeEvent(
                event_id="e-2", cursor=2, session_id="s-1", invocation_id="i-1", run_id=state.run_id,
                group_chat_id="gc-1", agent_id="a-1", phase="independent_analysis", type="text_completed",
                payload={"content": "second"}, timestamp=2.0,
            ).model_dump(mode="json"))
            assert "second" in await response.body_iterator.__anext__()
            state.status = "completed"
            await response.body_iterator.__anext__()

        asyncio.run(consume())
    finally:
        runs.run_store = previous
