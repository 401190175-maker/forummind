"""启动级 API 面回归保护测试。

锁定现有 API 面（/、/health、/version 与 CORS 配置，以及
创建课题组 API `POST /group-chats`），防止后续任务新增未设计
的业务路由（demo reset、Agent、Memory、文件上传、群聊查询等）
或让 `app.main` / `app.schemas` 依赖 Domain Schema 时无意改变启动行为。
"""

import ast
import inspect

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import BaseModel

import app.main as main_module
import app.schemas as startup_schemas
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
    "/runs/{run_id}/candidates": {"get"},
    "/runs/{run_id}/candidates/{candidate_id}/approve": {"post"},
    "/runs/{run_id}/candidates/{candidate_id}/reject": {"post"},
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
    "/group-chats/{group_chat_id}/experiment-datasets/preview": {"post"},
    "/group-chats/{group_chat_id}/experiment-datasets": {"post", "get"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions": {"get"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analysis": {"post"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analyses": {"get"},
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions/{version}/source": {"get"},
    "/documents/{document_id}": {"get"},
    "/documents/{document_id}/download": {"get"},
    "/group-chats/{group_chat_id}/tasks": {"post", "get"},
}

# 业务路由关键字：任一出现在「未列入 allowlist」的路由路径中即视为 API 面被破坏。
_BUSINESS_ROUTE_KEYWORDS = (
    "demo",
    "memory",
    "file",
    "artifact",
    "meeting",
    "message",
    "start",
    "status",
)


def _imported_domain_names(module: object) -> set[str]:
    """返回模块源码中导入的 `app.domain` 相关名称（AST 解析，忽略注释）。"""
    tree = ast.parse(inspect.getsource(module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return {
        name
        for name in imported
        if name == "app.domain" or name.startswith("app.domain.")
    }


def test_openapi_route_surface_is_exactly_expected() -> None:
    """OpenAPI 路由面恰好为 allowlist（启动级 + 创建课题组 + Run API + demo-safe 消息/澄清）。"""
    paths = app.openapi()["paths"]
    assert set(paths) == set(_EXPECTED_ROUTES)
    for path, methods in _EXPECTED_ROUTES.items():
        assert set(paths[path]) == methods


def test_no_unplanned_business_routes_added() -> None:
    """未新增 allowlist 之外的 demo reset、Agent、Memory、文件上传、群聊查询等未设计路由。"""
    allowed = set(_EXPECTED_ROUTES)
    for path in app.openapi()["paths"]:
        if path in allowed:
            continue  # allowlist 内的 demo-safe 路由（含 /messages）合法
        lowered = path.lower()
        assert not any(keyword in lowered for keyword in _BUSINESS_ROUTE_KEYWORDS)


def test_root_returns_service_info() -> None:
    """根路径返回基础服务信息。"""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "forummind-api"
    assert "message" in data


def test_health_fields_keep_startup_semantics() -> None:
    """/health 响应字段保持启动级语义（状态、服务名、环境）。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"status", "service", "environment"}
    assert data["status"] == "ok"
    assert data["service"] == "forummind-api"
    assert data["environment"] == "development"


def test_version_fields_keep_startup_semantics() -> None:
    """/version 响应字段保持启动级语义（服务名、版本、环境）。"""
    resp = client.get("/version")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"service", "version", "environment"}
    assert data["service"] == "forummind-api"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"


def test_cors_middleware_uses_default_local_origin_and_get_post() -> None:
    """CORS 中间件仍按现有配置工作：默认仅本地来源、允许 GET 与 POST。"""
    middlewares = [
        item for item in app.user_middleware if item.cls is CORSMiddleware
    ]
    assert len(middlewares) == 1
    options = middlewares[0].kwargs
    assert options["allow_origins"] == ["http://localhost:3000"]
    assert options["allow_methods"] == ["GET", "POST", "PATCH", "PUT", "DELETE"]
    assert options["allow_credentials"] is False


def test_cors_echoes_allowed_origin_only() -> None:
    """CORS 行为：允许默认来源，拒绝未知来源。"""
    allowed = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert (
        allowed.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )

    unknown = client.get(
        "/health",
        headers={"Origin": "http://untrusted.example.com"},
    )
    assert "access-control-allow-origin" not in unknown.headers


def test_main_module_does_not_import_domain_schema() -> None:
    """`app.main` 不导入 Domain Schema。"""
    assert _imported_domain_names(main_module) == set()


def test_startup_schemas_module_holds_only_health_and_version() -> None:
    """`app.schemas` 仅保存 HealthResponse/VersionResponse，且不导入 Domain Schema。"""
    assert _imported_domain_names(startup_schemas) == set()
    defined_names = {
        name
        for name, value in vars(startup_schemas).items()
        if not name.startswith("__") and inspect.getmodule(value) is startup_schemas
    }
    assert defined_names == {"HealthResponse", "VersionResponse"}
    assert issubclass(startup_schemas.HealthResponse, BaseModel)
    assert issubclass(startup_schemas.VersionResponse, BaseModel)
