"""合成 Demo 数据包模块的 API 面回归保护测试。

锁定 API 面：合成 Demo 数据包模块是后端内部能力，不得新增
业务路由（`/demo/reset`、`/demo/package`、`/projects/from-demo` 等），
也不得改变 `/`、`/health`、`/version` 与 CORS 行为（proposal §5、design §5）。
允许的路由面为启动级三个 GET 端点 + 创建课题组 API `POST /group-chats`
（proposal §4 的 allowlist 更新：启动级三个 GET 端点加本轮创建 API）。
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 允许的完整路由面（路径 -> 允许的方法集合）：
# 启动级三个 GET 端点 + 创建课题组 API `POST /group-chats` + Run API
# + 新原型对齐的 demo-safe 消息 / 任务澄清路由。
_EXPECTED_ROUTES = {
    "/": {"get"},
    "/health": {"get"},
    "/version": {"get"},
    "/group-chats": {"get", "post"},
    "/group-chats/{group_chat_id}": {"get", "delete"},
    "/group-chats/{group_chat_id}/meeting-schedule": {"get", "put"},
    "/group-chats/{group_chat_id}/runs": {"post"},
    "/group-chats/{group_chat_id}/messages": {"post", "get"},
    "/group-chats/{group_chat_id}/task-clarifications": {"post", "get"},
    "/group-chats/{group_chat_id}/task-clarifications/{clarification_id}/answers": {"post"},
    "/group-chats/{group_chat_id}/task-clarifications/{clarification_id}/formal-task": {"post"},
    "/group-chats/{group_chat_id}/members/{member_id}/configuration": {"patch"},
    "/runs/{run_id}": {"get"},
    "/runs/{run_id}/meeting-events": {"get"},
    "/runs/{run_id}/meeting-messages": {"post"},
    "/runs/{run_id}/decision": {"post"},
    "/runs/{run_id}/experiment-results": {"post"},
    "/agents": {"get", "post"},
    "/agents/{agent_id}": {"patch"},
    "/agents/{agent_id}/test": {"post"},
    "/group-chats/{group_chat_id}/meeting-rehearsals": {"post"},
    "/meeting-rehearsals/{session_id}": {"get"},
    "/meeting-rehearsals/{session_id}/answers": {"post"},
    "/meeting-rehearsals/{session_id}/preparation-package": {"post"},
    "/runtime-settings": {"get", "put", "delete"},
    "/group-chats/{group_chat_id}/documents": {"post", "get"},
    "/group-chats/{group_chat_id}/documents/{document_id}/index": {"post"},
    "/group-chats/{group_chat_id}/experiment-datasets": {"post", "get"},
    "/group-chats/{group_chat_id}/experiment-datasets/preview": {"post"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions": {"get"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analysis": {"post"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analyses": {"get"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions/{version}/source": {"get"},
    "/documents/{document_id}": {"get"},
    "/documents/{document_id}/download": {"get"},
    "/group-chats/{group_chat_id}/tasks": {"post", "get"},
    "/runs/{run_id}/candidates": {"get"},
    "/runs/{run_id}/candidates/{candidate_id}/approve": {"post"},
    "/runs/{run_id}/candidates/{candidate_id}/reject": {"post"},
}

# Demo 业务路由关键字：任一出现在路由路径中即视为 API 面被破坏。
_DEMO_ROUTE_KEYWORDS = ("demo", "reset", "from-demo", "package")


def test_openapi_route_surface_is_exactly_expected() -> None:
    """OpenAPI 路由面恰好为 allowlist（启动级 + 创建课题组 + Run API + demo-safe 消息/澄清）。"""
    paths = app.openapi()["paths"]
    assert set(paths) == set(_EXPECTED_ROUTES)
    for path, methods in _EXPECTED_ROUTES.items():
        assert set(paths[path]) == methods


def test_no_demo_business_routes_added() -> None:
    """未新增 /demo/reset、/demo/package、/projects/from-demo 等业务路由。"""
    for path in app.openapi()["paths"]:
        if path in _EXPECTED_ROUTES:
            continue
        lowered = path.lower()
        assert not any(keyword in lowered for keyword in _DEMO_ROUTE_KEYWORDS)


def test_health_and_version_still_work() -> None:
    """/health 与 /version 仍返回启动级语义。"""
    health = client.get("/health")
    assert health.status_code == 200
    assert set(health.json()) == {"status", "service", "environment"}

    version = client.get("/version")
    assert version.status_code == 200
    assert set(version.json()) == {"service", "version", "environment"}
    assert version.json()["version"] == "0.1.0"


def test_demo_routes_do_not_exist() -> None:
    """Demo 业务路由即使被请求也不存在（404，而不是被静默实现）。"""
    for path in ("/demo/reset", "/demo/package", "/projects/from-demo"):
        assert client.get(path).status_code == 404
