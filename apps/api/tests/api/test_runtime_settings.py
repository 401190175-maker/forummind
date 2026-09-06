"""Runtime settings HTTP boundary tests."""

from fastapi.testclient import TestClient

from app.agent_runtime.config import runtime_config
from app.main import app


def test_runtime_settings_route_returns_non_sensitive_status() -> None:
    client = TestClient(app)
    runtime_config.clear()

    response = client.put(
        "/runtime-settings",
        json={
            "provider": "pi",
            "base_url": "http://pi.local/invoke",
            "model": "research-model",
            "api_key": "secret-value",
        },
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["model"] == "research-model"
    assert "secret-value" not in response.text
    assert client.get("/runtime-settings").json()["configured"] is True


def test_runtime_settings_clear_makes_runtime_unavailable() -> None:
    client = TestClient(app)
    runtime_config.configure(
        provider="pi",
        base_url="http://pi.local/invoke",
        model="research-model",
        api_key="secret-value",
    )

    response = client.delete("/runtime-settings")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert client.get("/runtime-settings").json()["configured"] is False
