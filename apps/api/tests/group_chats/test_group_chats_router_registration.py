"""group_chats router 注册测试（Task 14）。

覆盖：`app.main` 注册 `POST /group-chats` 后 OpenAPI 包含该路径，
启动级 `GET /`、`/health`、`/version` 行为不变，CORS 支持 POST
跨域预检，且 `main.py` 不承载业务逻辑。
"""

import ast
import inspect

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app

client = TestClient(app)

_VALID_PAYLOAD = {
    "topic_name": "废弃泥浆基泡沫混凝土",
    "topic_summary": "研究废弃泥浆基泡沫混凝土的机理与性能",
    "member_selection": {
        "postdoc": {
            "selection_mode": "existing",
            "agent_ids": ["agent-postdoc-1"],
        },
        "phd_student": {
            "selection_mode": "existing",
            "agent_ids": ["agent-phd-1"],
        },
        "master_student": {
            "selection_mode": "generate",
            "count": 3,
        },
    },
}


def test_openapi_contains_post_group_chats() -> None:
    """OpenAPI 包含 POST /group-chats。"""
    paths = app.openapi()["paths"]
    assert "/group-chats" in paths
    assert "post" in paths["/group-chats"]


def test_startup_routes_still_work() -> None:
    """GET /、/health、/version 仍可用且语义不变。"""
    assert client.get("/").status_code == 200
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    version = client.get("/version")
    assert version.status_code == 200
    assert version.json()["version"] == "0.1.0"


def test_post_group_chats_through_registered_app() -> None:
    """通过注册后的真实 app 调用 POST /group-chats 成功。"""
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["group_chat"]["id"].startswith("gc-")


def test_cors_preflight_allows_post() -> None:
    """CORS 预检允许 POST 跨域请求。"""
    resp = client.options(
        "/group-chats",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods
    assert "GET" in allow_methods


def test_cors_get_behavior_unchanged() -> None:
    """既有 CORS GET 行为不变。"""
    resp = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_main_module_registers_router_without_business_logic() -> None:
    """main.py 只注册 router，不包含创建课题组业务逻辑。"""
    source = inspect.getsource(main_module)
    for forbidden in (
        "create_group_chat(",
        "build_chat_members",
        "build_demo_objects",
        "load_demo_package",
        "DemoObjectBundle",
    ):
        assert forbidden not in source
    tree = ast.parse(source)
    calls = [
        (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    ]
    assert "include_router" in calls
