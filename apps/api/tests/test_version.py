"""`/version` 接口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_version_returns_service_info() -> None:
    resp = client.get("/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "forummind-api"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"
