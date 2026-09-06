"""课题组群聊读取 API 测试（可信前端 Task 1）。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.group_chats import router
from app.group_chats import creation_service as creation_service_module
from app.storage.sqlite_store import SQLiteStore


_test_app = FastAPI()
_test_app.include_router(router)
client = TestClient(_test_app)

_PAYLOAD = {
    "topic_name": "可信前端读取测试课题组",
    "topic_summary": "验证课题组列表和详情读取来自创建服务的完整响应",
    "member_selection": {
        "postdoc": {"selection_mode": "generate", "count": 1},
        "phd_student": {"selection_mode": "generate", "count": 1},
        "master_student": {
            "selection_mode": "generate",
            "count": 3,
        },
    },
}


def test_list_group_chats_returns_created_response() -> None:
    """列表读取包含刚由同一 API 创建的课题组完整响应。"""
    created = client.post("/group-chats", json=_PAYLOAD)
    assert created.status_code == 200
    group_id = created.json()["group_chat"]["id"]

    listed = client.get("/group-chats")

    assert listed.status_code == 200
    assert any(item["group_chat"]["id"] == group_id for item in listed.json())


def test_list_group_chats_query_matches_visible_group_fields_case_insensitively() -> None:
    """列表查询按课题卡片可见字段做大小写不敏感的子串匹配。"""
    created = client.post(
        "/group-chats",
        json={
            **_PAYLOAD,
            "topic_name": "Mechanism Search Topic",
            "topic_summary": "UNIQUE-PORE-SEARCH: Pore structure and strength",
            "member_selection": {
                "postdoc": {"selection_mode": "generate", "count": 1},
                "phd_student": {"selection_mode": "generate", "count": 1},
                "master_student": {"selection_mode": "generate", "count": 3},
            },
        },
    )
    assert created.status_code == 200
    group_id = created.json()["group_chat"]["id"]

    matched = client.get("/group-chats", params={"query": "unique-pore-search"})
    assert matched.status_code == 200
    assert [item["group_chat"]["id"] for item in matched.json()] == [group_id]

    role_match = client.get("/group-chats", params={"query": "硕士"})
    assert role_match.status_code == 200
    assert any(item["group_chat"]["id"] == group_id for item in role_match.json())


def test_list_group_chats_query_returns_empty_for_no_match() -> None:
    created = client.post(
        "/group-chats",
        json={
            **_PAYLOAD,
            "member_selection": {
                "postdoc": {"selection_mode": "generate", "count": 1},
                "phd_student": {"selection_mode": "generate", "count": 1},
                "master_student": {"selection_mode": "generate", "count": 3},
            },
        },
    )
    assert created.status_code == 200

    response = client.get("/group-chats", params={"query": "不存在的课题关键词"})

    assert response.status_code == 200
    assert response.json() == []


def test_get_group_chat_returns_complete_response() -> None:
    """详情读取返回创建响应声明的持久化边界。"""
    created = client.post("/group-chats", json=_PAYLOAD)
    assert created.status_code == 200
    group_id = created.json()["group_chat"]["id"]

    detail = client.get(f"/group-chats/{group_id}")

    assert detail.status_code == 200
    assert detail.json()["group_chat"]["id"] == group_id
    assert detail.json()["persistence"] == "sqlite"


def test_get_unknown_group_chat_returns_404() -> None:
    """未知课题组详情不能被误表示为存在。"""
    response = client.get("/group-chats/not-created")

    assert response.status_code == 404
    assert response.json()["detail"] == "课题组不存在"


def test_list_group_chats_recovers_after_process_cache_clear(tmp_path) -> None:
    """列表读取必须在清空进程缓存后仍从 SQLite 返回课题组。"""
    store = SQLiteStore(tmp_path / "group-chats.db")
    store.initialize()
    previous_store = creation_service_module._persistence_store
    creation_service_module.configure_persistence(store)
    try:
        created = client.post("/group-chats", json=_PAYLOAD)
        assert created.status_code == 200
        group_id = created.json()["group_chat"]["id"]
        creation_service_module._created_group_chats.clear()

        listed = client.get("/group-chats")

        assert listed.status_code == 200
        assert any(item["group_chat"]["id"] == group_id for item in listed.json())
    finally:
        creation_service_module.reset_created_group_chats()
        creation_service_module.configure_persistence(previous_store)
        store.close()


def test_detail_reads_repository_instead_of_stale_process_cache(tmp_path) -> None:
    """详情不能在 SQLite 已删除后继续把内存缓存当作服务端事实。"""
    store = SQLiteStore(tmp_path / "group-chats.db")
    store.initialize()
    previous_store = creation_service_module._persistence_store
    creation_service_module.configure_persistence(store)
    try:
        created = client.post("/group-chats", json=_PAYLOAD)
        assert created.status_code == 200
        group_id = created.json()["group_chat"]["id"]

        creation_service_module._group_chat_repository.delete_all()

        detail = client.get(f"/group-chats/{group_id}")

        assert detail.status_code == 404
        assert detail.json()["detail"] == "课题组不存在"
    finally:
        creation_service_module.reset_created_group_chats()
        creation_service_module.configure_persistence(previous_store)
        store.close()
