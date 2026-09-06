from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import runs
from app.api.runtime_events import router
from app.orchestration.run_store import RunStore


def test_abort_marks_run_terminated():
    app = FastAPI()
    app.include_router(router)
    previous = runs.run_store
    store = RunStore()
    runs.run_store = store
    try:
        state = store.create("gc-1", "live")
        response = TestClient(app).post(f"/runs/{state.run_id}/control", json={"action": "abort"})
        assert response.status_code == 200
        assert response.json()["status"] == "terminated"
    finally:
        runs.run_store = previous
