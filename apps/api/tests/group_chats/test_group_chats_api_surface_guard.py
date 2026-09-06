"""API Surface 边界保护测试（Task 15）。

证明本轮只新增已设计的课题组读取与 Agent 生命周期 API，没有误暴露其他后续 API
（未设计的群聊查询、消息发送、启动团队、产物浏览、团队状态、课题组动态、
demo reset、Agent、Memory、文件上传、会议纪要生成等）。
"""

from app.main import app


_ALLOWED_REHEARSAL_ROUTES = {
    "/group-chats/{group_chat_id}/meeting-rehearsals",
    "/meeting-rehearsals/{session_id}",
    "/meeting-rehearsals/{session_id}/answers",
    "/meeting-rehearsals/{session_id}/preparation-package",
}

_ALLOWED_FORMAL_MEETING_ROUTES = {
    "/runs/{run_id}/meeting-events",
    "/runs/{run_id}/meeting-messages",
}

_ALLOWED_CANDIDATE_ROUTES = {
    "/runs/{run_id}/candidates",
    "/runs/{run_id}/candidates/{candidate_id}/approve",
    "/runs/{run_id}/candidates/{candidate_id}/reject",
}


def test_group_chat_collection_routes_present() -> None:
    """OpenAPI 中存在课题组创建与列表路由。"""
    paths = app.openapi()["paths"]
    assert "/group-chats" in paths
    assert set(paths["/group-chats"]) == {"post", "get"}


def test_group_chat_read_routes_are_limited_to_collection_detail_and_messages() -> None:
    """只允许课题组集合、详情和消息列表的 GET 读取路由。"""
    paths = app.openapi()["paths"]
    assert set(paths["/group-chats/{group_chat_id}"]) == {"get", "delete"}
    allowed_get_paths = {
        "/group-chats",
        "/group-chats/{group_chat_id}",
        "/group-chats/{group_chat_id}/messages",
        "/group-chats/{group_chat_id}/task-clarifications",
        "/group-chats/{group_chat_id}/meeting-schedule",
        "/group-chats/{group_chat_id}/documents",
        "/group-chats/{group_chat_id}/tasks",
        "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions",
        "/group-chats/{group_chat_id}/experiment-datasets",
        "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analyses",
        "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions/{version}/source",
    }
    for path, methods in paths.items():
        assert not (
            path.startswith("/group-chats/")
            and "get" in methods
            and path not in allowed_get_paths
        ), path


def test_group_chat_messages_routes_present() -> None:
    """OpenAPI 明确包含 demo-safe 消息路由：POST/GET /group-chats/{id}/messages。"""
    paths = app.openapi()["paths"]
    messages_path = "/group-chats/{group_chat_id}/messages"
    assert messages_path in paths
    assert set(paths[messages_path]) == {"post", "get"}


def test_no_group_chat_other_message_subroutes() -> None:
    """除 /messages 外，不存在搜索 / 附件 / 撤回等未设计消息子路由。"""
    paths = app.openapi()["paths"]
    for path in paths:
        if path == "/group-chats/{group_chat_id}/messages":
            continue
        assert "/messages/" not in path and not path.endswith("/messages"), path


def test_group_chat_task_clarification_route_present() -> None:
    """OpenAPI 明确包含 demo-safe 任务澄清路由：POST /group-chats/{id}/task-clarifications。"""
    paths = app.openapi()["paths"]
    clarification_path = "/group-chats/{group_chat_id}/task-clarifications"
    assert clarification_path in paths
    assert set(paths[clarification_path]) == {"post", "get"}


def test_startup_routes_present() -> None:
    """surface guard 包含现有启动级路由。"""
    paths = app.openapi()["paths"]
    assert set(paths.get("/", {})) == {"get"}
    assert set(paths.get("/health", {})) == {"get"}
    assert set(paths.get("/version", {})) == {"get"}


def test_run_api_routes_present() -> None:
    """surface guard 包含现有 Run API 路由。"""
    paths = app.openapi()["paths"]
    assert set(paths.get("/group-chats/{group_chat_id}/runs", {})) == {"post"}
    assert set(paths.get("/runs/{run_id}", {})) == {"get"}
    assert set(paths.get("/runs/{run_id}/meeting-events", {})) == {"get"}
    assert set(paths.get("/runs/{run_id}/meeting-messages", {})) == {"post"}
    assert set(paths.get("/runs/{run_id}/decision", {})) == {"post"}
    assert set(paths.get("/runs/{run_id}/experiment-results", {})) == {"post"}
    assert set(paths.get("/runs/{run_id}/candidates", {})) == {"get"}
    assert set(paths.get("/runs/{run_id}/candidates/{candidate_id}/approve", {})) == {"post"}
    assert set(paths.get("/runs/{run_id}/candidates/{candidate_id}/reject", {})) == {"post"}
    assert set(paths.get("/agents", {})) == {"get", "post"}
    assert set(paths.get("/agents/{agent_id}", {})) == {"patch"}
    assert set(paths.get("/agents/{agent_id}/test", {})) == {"post"}


def test_no_undesigned_persistence_or_runtime_routes() -> None:
    """不允许未设计的数据库、文件上传、RAG、Pi HTTP 路由。"""
    paths = app.openapi()["paths"]
    for path in paths:
        if path in _ALLOWED_CANDIDATE_ROUTES:
            continue
        lowered = path.lower()
        for keyword in (
            "upload",
            "file",
            "database",
            "db/",
            "rag",
            "pi/",
            "pi_runtime",
            "streaming",
            "candidate",
        ):
            assert keyword not in lowered, f"{keyword} in {path}"


def test_no_group_chat_start_route() -> None:
    """不存在 POST /group-chats/{id}/start（启动团队 API 未实现）。"""
    paths = app.openapi()["paths"]
    assert not any(path.endswith("/start") for path in paths)


def test_no_group_chat_artifacts_route() -> None:
    """不存在 GET /group-chats/{id}/artifacts（产物浏览未实现）。"""
    paths = app.openapi()["paths"]
    assert not any("/artifacts" in path for path in paths)


def test_no_group_chat_status_route() -> None:
    """不存在 GET /group-chats/{id}/status（团队状态未实现）。"""
    paths = app.openapi()["paths"]
    assert not any(path.endswith("/status") for path in paths)


def test_no_group_chat_activity_route() -> None:
    """不存在 GET /group-chats/{id}/activity（课题组动态未实现）。"""
    paths = app.openapi()["paths"]
    assert not any("/activity" in path for path in paths)


def test_no_demo_reset_or_demo_package_routes() -> None:
    """不存在 /demo/reset 与 /demo/package。"""
    paths = app.openapi()["paths"]
    assert not any(path.startswith("/demo") for path in paths)


def test_no_projects_from_demo_route() -> None:
    """不存在 /projects/from-demo。"""
    paths = app.openapi()["paths"]
    assert not any(path.startswith("/projects") for path in paths)


def test_no_agent_memory_file_or_meeting_routes() -> None:
    """不存在未设计的 Agent、Memory、文件上传或会议纪要生成路径。"""
    paths = app.openapi()["paths"]
    for path in paths:
        if (
            path.startswith("/agents")
            or path in _ALLOWED_REHEARSAL_ROUTES
            or path in _ALLOWED_FORMAL_MEETING_ROUTES
            or path == "/group-chats/{group_chat_id}/meeting-schedule"
        ):
            continue  # 合法：Agent 生命周期 API 与设计内的预演 API
        lowered = path.lower()
        for keyword in (
            "agent",
            "memory",
            "upload",
            "file",
            "meeting",
            "minutes",
            "discussion",
        ):
            assert keyword not in lowered
