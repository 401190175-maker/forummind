"""Agent lifecycle HTTP API behavior."""

from fastapi.testclient import TestClient

from app.agent_runtime.pi_runtime import PiRuntime
from app.agents import service as agent_service
from app.agents.service import AgentService
from app.main import app
from app.storage.sqlite_store import SQLiteStore


class FakePiClient:
    async def invoke(self, request: dict) -> dict:
        return {"agent_id": request["agent_id"], "content": "Pi 候选回答"}


def _profile_payload(agent_id: str = "agent-api") -> dict:
    return {
        "agent_id": agent_id,
        "name": "API Agent",
        "role": "master_student",
    }


def test_agent_lifecycle_and_test_endpoint(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "api.db")
    store.initialize()
    configured = AgentService(store=store, runtime=PiRuntime(FakePiClient()))
    monkeypatch.setattr(agent_service, "_default_service", configured)
    client = TestClient(app)

    created = client.post("/agents", json=_profile_payload())
    assert created.status_code == 200
    assert created.json()["enabled"] is True
    assert any(
        item["agent_id"] == "agent-api"
        for item in client.get("/agents").json()["agents"]
    )

    assert client.patch("/agents/agent-api", json={"enabled": False}).status_code == 200
    disabled = client.post("/agents/agent-api/test", json={"task": "测试"})
    assert disabled.status_code == 409
    assert client.patch("/agents/agent-api", json={"enabled": True}).status_code == 200

    tested = client.post("/agents/agent-api/test", json={"task": "测试"})
    assert tested.status_code == 200
    assert tested.json()["status"] == "ready"
    assert tested.json()["agent_id"] == "agent-api"
    assert tested.json()["runtime"] == "pi"
    store.close()


def test_agent_responses_project_latest_persisted_test_status(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "api.db")
    store.initialize()
    configured = AgentService(store=store, runtime=PiRuntime(FakePiClient()))
    monkeypatch.setattr(agent_service, "_default_service", configured)
    client = TestClient(app)

    created = client.post("/agents", json=_profile_payload("agent-status"))
    assert created.status_code == 200
    assert created.json()["latest_test"] is None
    before = client.get("/agents").json()["agents"]
    assert next(item for item in before if item["agent_id"] == "agent-status")["latest_test"] is None

    tested = client.post("/agents/agent-status/test", json={"task": "测试状态"})
    assert tested.status_code == 200

    listed = client.get("/agents").json()["agents"]
    latest = next(item for item in listed if item["agent_id"] == "agent-status")["latest_test"]
    assert latest["test_id"] == tested.json()["test_id"]
    assert latest["status"] == "ready"

    updated = client.patch("/agents/agent-status", json={"name": "已测试 Agent"})
    assert updated.status_code == 200
    assert updated.json()["latest_test"]["test_id"] == tested.json()["test_id"]
    store.close()


def test_agent_api_maps_duplicate_missing_and_blank_task_errors(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "api.db")
    store.initialize()
    monkeypatch.setattr(agent_service, "_default_service", AgentService(store=store))
    client = TestClient(app)

    assert client.post("/agents", json=_profile_payload("agent-errors")).status_code == 200
    assert client.post("/agents", json=_profile_payload("agent-errors")).status_code == 409
    assert client.patch("/agents/missing", json={"name": "x"}).status_code == 404
    assert client.post("/agents/missing/test", json={"task": "x"}).status_code == 404
    assert client.post("/agents/agent-errors/test", json={"task": "  "}).status_code == 422
    store.close()


def test_agent_api_returns_unavailable_as_business_status(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "api.db")
    store.initialize()
    monkeypatch.setattr(agent_service, "_default_service", AgentService(store=store))
    monkeypatch.setenv("AGENT_RUNTIME", "pi")
    monkeypatch.setenv("PI_ENABLED", "false")
    client = TestClient(app)

    assert client.post("/agents", json=_profile_payload("agent-unavailable")).status_code == 200
    response = client.post(
        "/agents/agent-unavailable/test", json={"task": "测试不可用 Pi"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert "PI_ENABLED" in response.json()["error"]
    store.close()
