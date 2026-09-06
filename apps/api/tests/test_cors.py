"""本地 CORS 配置测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_allows_local_web_origin() -> None:
    resp = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_does_not_allow_unknown_origin() -> None:
    resp = client.get(
        "/health",
        headers={"Origin": "http://untrusted.example.com"},
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
