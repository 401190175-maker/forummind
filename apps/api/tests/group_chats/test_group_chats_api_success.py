"""`POST /group-chats` 成功路径测试（Task 12）。

路由尚未注册到 `app.main`（Task 14），本文件用独立 FastAPI app
挂载 router 验证成功响应契约；路由函数不承载业务拼装逻辑。
"""

import ast
import inspect

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.group_chats import create_group_chat_route, router
from app.group_chats.schemas import CreateGroupChatResponse

_test_app = FastAPI()
_test_app.include_router(router)
client = TestClient(_test_app)

_VALID_PAYLOAD = {
    "topic_name": "废弃泥浆基泡沫混凝土",
    "topic_summary": "研究废弃泥浆基泡沫混凝土的机理与性能",
    "data_space": "synthetic",
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


def test_post_group_chats_returns_200() -> None:
    """POST /group-chats 合法请求返回 200。"""
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 200


def test_success_response_conforms_to_schema() -> None:
    """成功响应符合 CreateGroupChatResponse 契约。"""
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 200
    parsed = CreateGroupChatResponse.model_validate(resp.json())
    assert parsed.persistence == "sqlite"
    assert parsed.agent_automation == "disabled"


def test_response_contains_group_chat_id_members_and_messages() -> None:
    """响应包含 group_chat.id、成员列表和初始系统消息。"""
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    data = resp.json()
    assert data["group_chat"]["id"].startswith("gc-")
    assert len(data["members"]) == 5
    assert len(data["initial_messages"]) >= 1
    assert data["members"][0]["status"] == "active"
    assert data["members"][-1]["status"] == "pending_generation"


def test_response_contains_research_objects() -> None:
    """响应包含 project / research_question / research_state。"""
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    data = resp.json()
    assert data["project"] is not None
    assert data["project"]["data_space"] == "synthetic"
    assert data["research_question"] is not None
    assert data["research_state"] is not None
    assert data["research_state"]["data_space"] == "synthetic"


def test_response_contains_not_started_team_run() -> None:
    """响应包含未启动的 team_run 占位。"""
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    data = resp.json()
    assert data["team_run"]["status"] == "not_started"
    assert data["team_run"]["automation_enabled"] is False


def test_route_function_contains_no_business_assembly() -> None:
    """路由函数不包含成员解析、demo 对象构造或业务拼装逻辑。"""
    source = inspect.getsource(create_group_chat_route)
    for forbidden in (
        "build_chat_members",
        "build_demo_objects",
        "load_demo_package",
        "ChatMember(",
        "DemoObjectBundle",
    ):
        assert forbidden not in source
    tree = ast.parse(source)
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "create_group_chat" in calls
