"""`POST /group-chats` 错误响应测试（Task 13）。

覆盖主要请求错误场景的 HTTP 422 回归；所有错误都不触发
数据库写入、Agent 执行或外部网络调用（错误来自 Pydantic
校验与内存内业务校验）。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.group_chats import router

_test_app = FastAPI()
_test_app.include_router(router)
client = TestClient(_test_app)


def _payload(member_selection: dict | None = None, **overrides) -> dict:
    payload = {
        "topic_name": "废弃泥浆基泡沫混凝土",
        "topic_summary": "研究废弃泥浆基泡沫混凝土的机理与性能",
        "member_selection": (
            member_selection
            if member_selection is not None
            else {
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
            }
        ),
    }
    payload.update(overrides)
    return payload


def test_empty_topic_name_returns_422() -> None:
    resp = client.post("/group-chats", json=_payload(topic_name=""))
    assert resp.status_code == 422


def test_blank_topic_name_returns_422() -> None:
    resp = client.post("/group-chats", json=_payload(topic_name="   "))
    assert resp.status_code == 422


def test_empty_topic_summary_returns_422() -> None:
    resp = client.post("/group-chats", json=_payload(topic_summary=""))
    assert resp.status_code == 422


def test_empty_member_selection_returns_422() -> None:
    resp = client.post("/group-chats", json=_payload(member_selection={}))
    assert resp.status_code == 422


def test_missing_member_selection_returns_422() -> None:
    payload = _payload()
    del payload["member_selection"]
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422


def test_invalid_selection_mode_returns_422() -> None:
    payload = _payload()
    payload["member_selection"]["postdoc"]["selection_mode"] = "unknown"
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422


def test_existing_mode_missing_agent_ids_returns_422() -> None:
    payload = _payload()
    payload["member_selection"]["postdoc"] = {"selection_mode": "existing"}
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422


def test_generate_mode_missing_count_returns_422() -> None:
    payload = _payload()
    payload["member_selection"]["master_student"] = {
        "selection_mode": "generate"
    }
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422


def test_missing_postdoc_returns_422() -> None:
    payload = _payload()
    del payload["member_selection"]["postdoc"]
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422


def test_missing_phd_student_returns_422() -> None:
    payload = _payload()
    del payload["member_selection"]["phd_student"]
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422


def test_less_than_three_masters_returns_422() -> None:
    payload = _payload()
    payload["member_selection"]["master_student"] = {
        "selection_mode": "generate",
        "count": 2,
    }
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422
    detail_text = str(resp.json()["detail"])
    assert "master_student" in detail_text


def test_unknown_agent_id_returns_422() -> None:
    payload = _payload()
    payload["member_selection"]["postdoc"]["agent_ids"] = ["agent-unknown-1"]
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422
    assert "agent-unknown-1" in resp.json()["detail"]


def test_agent_role_mismatch_returns_422() -> None:
    payload = _payload()
    # agent-ms-1 是 master_student，放在 postdoc 键下即角色不匹配。
    payload["member_selection"]["postdoc"]["agent_ids"] = ["agent-ms-1"]
    resp = client.post("/group-chats", json=payload)
    assert resp.status_code == 422
    assert "角色不匹配" in resp.json()["detail"]


def test_error_responses_are_json_with_detail() -> None:
    """422 响应为 JSON 且包含 detail 信息。"""
    resp = client.post("/group-chats", json=_payload(topic_name=""))
    assert resp.headers["content-type"].startswith("application/json")
    assert "detail" in resp.json()
