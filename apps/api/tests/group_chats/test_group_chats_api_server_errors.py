"""`POST /group-chats` 服务端错误映射测试（Validation Loop 补充）。

覆盖 design §11 的错误映射：成员/结构业务校验错误、非法或不存在的
demo 数据包 id -> 422；demo 数据包解析失败或 schema 配置错误 -> 500。
通过 monkeypatch 注入异常，直接验证 router 的错误映射逻辑。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.api.group_chats as group_chats_api
from app.demo_data.loader import (
    DemoPackageInvalidIdError,
    DemoPackageNotFoundError,
    DemoPackageParseError,
    DemoPackageValidationError,
)
from app.demo_data.package_schema import DemoDataPackage
from app.group_chats.creation_service import AgentRoleMismatchError

_test_app = FastAPI()
_test_app.include_router(group_chats_api.router)
client = TestClient(_test_app)

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


def _sample_validation_error() -> ValidationError:
    """构造一个真实的 Pydantic ValidationError 样例。"""
    try:
        DemoDataPackage.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("空数据包应触发 ValidationError")


def test_package_parse_error_maps_to_500(monkeypatch) -> None:
    """demo 数据包 JSON 解析失败 -> 500（内部配置错误）。"""
    def boom(_request):
        raise DemoPackageParseError("demo 数据包 JSON 解析失败")

    monkeypatch.setattr(group_chats_api, "create_group_chat", boom)
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 500


def test_package_schema_error_maps_to_500(monkeypatch) -> None:
    """demo 数据包 schema 校验失败 -> 500（内部配置错误）。"""
    def boom(_request):
        raise DemoPackageValidationError(
            "demo 数据包 schema 校验失败",
            validation_error=_sample_validation_error(),
        )

    monkeypatch.setattr(group_chats_api, "create_group_chat", boom)
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 500
    assert "demo 数据包配置错误" in resp.json()["detail"]


def test_package_not_found_maps_to_422(monkeypatch) -> None:
    """未知 demo 数据包 -> 422（客户端指定了不存在的包）。"""
    def boom(_request):
        raise DemoPackageNotFoundError("Demo 数据包不存在: package_id='x'")

    monkeypatch.setattr(group_chats_api, "create_group_chat", boom)
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 422


def test_package_invalid_id_maps_to_422(monkeypatch) -> None:
    """非法 demo 数据包 id（路径穿越）-> 422。"""
    def boom(_request):
        raise DemoPackageInvalidIdError("非法的 Demo 数据包 package_id")

    monkeypatch.setattr(group_chats_api, "create_group_chat", boom)
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 422


def test_business_error_maps_to_422(monkeypatch) -> None:
    """业务校验错误（Agent 角色不匹配）-> 422，携带定位信息。"""
    def boom(_request):
        raise AgentRoleMismatchError(
            "Agent 角色不匹配: agent_id='agent-ms-1' 是 master_student，"
            "但成员选择角色键 'postdoc' 需要 postdoc"
        )

    monkeypatch.setattr(group_chats_api, "create_group_chat", boom)
    resp = client.post("/group-chats", json=_VALID_PAYLOAD)
    assert resp.status_code == 422
    assert "角色不匹配" in resp.json()["detail"]
