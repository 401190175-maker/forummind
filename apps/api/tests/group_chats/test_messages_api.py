"""消息与任务澄清 DTO 测试（tasks.md Task 12）。

Task 12 范围：消息 DTO（MentionTarget / CreateMessageRequest /
ChatMessageRecord）；任务澄清 DTO 在 Task 15 的
`test_task_clarification.py` 覆盖。本文件同时承载 Task 13/14
的 store 与 API 路由测试。
"""
from typing import Any

import pytest
from pydantic import ValidationError

from app.group_chats.schemas import (
    ChatMessage,
    ChatMessageRecord,
    CreateMessageRequest,
    MentionTarget,
)
from app.storage.sqlite_store import SQLiteStore  # noqa: E402


def _mention(target_type: str = "all", **overrides: Any) -> dict:
    data = {"target_type": target_type, "target_id": "all", "label": "全体成员"}
    data.update(overrides)
    return data


# ---------------- MentionTarget ----------------

def test_mention_target_all() -> None:
    target = MentionTarget.model_validate(_mention())
    assert target.target_type == "all"
    assert target.target_id == "all"
    assert target.label == "全体成员"


def test_mention_target_role_and_member() -> None:
    role = MentionTarget.model_validate(
        _mention("role", target_id="role:phd_student", label="博士")
    )
    assert role.target_type == "role"
    member = MentionTarget.model_validate(
        _mention("member", target_id="gc-x:master_student:agent-ms-1", label="硕士A")
    )
    assert member.target_type == "member"


@pytest.mark.parametrize("bad_type", ["allx", "everyone", "", 123])
def test_mention_target_rejects_invalid_type(bad_type: Any) -> None:
    with pytest.raises(ValidationError):
        MentionTarget.model_validate(_mention(bad_type))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field", ["target_type", "target_id", "label"]
)
def test_mention_target_rejects_blank_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        MentionTarget.model_validate(_mention(**{field: "   "}))


# ---------------- CreateMessageRequest ----------------

def test_create_message_request_minimal() -> None:
    request = CreateMessageRequest.model_validate({"content": "请帮我分析强度下降机制"})
    assert request.content == "请帮我分析强度下降机制"
    assert request.mention is None


def test_create_message_request_with_mention() -> None:
    request = CreateMessageRequest.model_validate(
        {"content": "帮我整理文献", "mention": _mention("member", target_id="m1", label="硕士A")}
    )
    assert request.mention is not None
    assert request.mention.target_type == "member"


@pytest.mark.parametrize("bad_content", ["", "   ", None])
def test_create_message_request_empty_content_422(bad_content: Any) -> None:
    with pytest.raises(ValidationError):
        CreateMessageRequest.model_validate({"content": bad_content})


# ---------------- ChatMessageRecord ----------------

def test_chat_message_record_defaults_synthetic() -> None:
    record = ChatMessageRecord.model_validate(
        {
            "id": "msg-1",
            "group_chat_id": "gc-1",
            "content": "hello",
            "created_at": 1.0,
        }
    )
    assert record.sender_type == "user"
    assert record.data_space.value == "synthetic"
    assert record.mention is None


def test_chat_message_record_with_mention_and_sender() -> None:
    record = ChatMessageRecord.model_validate(
        {
            "id": "msg-2",
            "group_chat_id": "gc-1",
            "sender_type": "agent",
            "content": "收到",
            "mention": _mention("role", target_id="role:master_student", label="硕士"),
            "created_at": 2.0,
        }
    )
    assert record.sender_type == "agent"
    assert record.mention is not None


@pytest.mark.parametrize("bad_sender", ["admin", "bot", ""])
def test_chat_message_record_rejects_invalid_sender(bad_sender: Any) -> None:
    with pytest.raises(ValidationError):
        ChatMessageRecord.model_validate(
            {
                "id": "msg-3",
                "group_chat_id": "gc-1",
                "sender_type": bad_sender,
                "content": "x",
                "created_at": 1.0,
            }
        )


def test_chat_message_record_rejects_blank_content() -> None:
    with pytest.raises(ValidationError):
        ChatMessageRecord.model_validate(
            {
                "id": "msg-4",
                "group_chat_id": "gc-1",
                "content": "  ",
                "created_at": 1.0,
            }
        )


# ---------------- 现有 ChatMessage 系统消息 DTO 不受影响 ----------------

def test_existing_chat_message_system_dto_unchanged() -> None:
    """初始化系统消息 DTO 仍是原字段形状，message_type 固定 system。"""
    message = ChatMessage(
        id="gc-1:msg-1",
        group_chat_id="gc-1",
        content="课题组已创建",
    )
    assert message.message_type == "system"
    assert message.sender_type == "system"
    assert message.attachment_refs == []
    data = message.model_dump()
    assert set(data) == {
        "id", "group_chat_id", "message_type", "sender_type", "content",
        "attachment_refs",
    }


# ---------------- Task 13：in-memory message store ----------------

from app.group_chats import messages as messages_store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_messages():
    """每个用例前清空进程内消息 store（保证用例独立）。"""
    messages_store.reset_messages()
    yield
    messages_store.reset_messages()


def test_add_user_message_returns_record() -> None:
    request = CreateMessageRequest.model_validate(
        {"content": "帮我分析强度下降机制", "mention": _mention("member", target_id="m1", label="硕士A")}
    )
    record = messages_store.add_user_message("gc-1", request)
    assert record.id.startswith("msg-")
    assert record.group_chat_id == "gc-1"
    assert record.sender_type == "user"
    assert record.content == "帮我分析强度下降机制"
    assert record.mention is not None
    assert record.mention.target_type == "member"
    assert record.data_space.value == "synthetic"


def test_list_messages_in_creation_order() -> None:
    first = messages_store.add_user_message(
        "gc-1", CreateMessageRequest.model_validate({"content": "第一条"})
    )
    second = messages_store.add_user_message(
        "gc-1", CreateMessageRequest.model_validate({"content": "第二条"})
    )
    records = messages_store.list_messages("gc-1")
    assert [r.id for r in records] == [first.id, second.id]
    assert [r.content for r in records] == ["第一条", "第二条"]


def test_message_ids_monotonic_unique() -> None:
    ids = [
        messages_store.add_user_message(
            "gc-1", CreateMessageRequest.model_validate({"content": f"m{i}"})
        ).id
        for i in range(5)
    ]
    assert len(set(ids)) == 5
    assert ids == sorted(ids)


def test_messages_isolated_per_group_chat() -> None:
    messages_store.add_user_message(
        "gc-1", CreateMessageRequest.model_validate({"content": "a"})
    )
    assert messages_store.list_messages("gc-2") == []


def test_list_unknown_group_chat_returns_empty() -> None:
    assert messages_store.list_messages("gc-nope") == []


def test_reset_messages_clears_all() -> None:
    messages_store.add_user_message(
        "gc-1", CreateMessageRequest.model_validate({"content": "a"})
    )
    messages_store.reset_messages()
    assert messages_store.list_messages("gc-1") == []


def test_store_marks_all_messages_synthetic() -> None:
    messages_store.add_user_message(
        "gc-1", CreateMessageRequest.model_validate({"content": "x"})
    )
    messages_store.add_user_message(
        "gc-1", CreateMessageRequest.model_validate({"content": "y"})
    )
    assert all(
        r.data_space.value == "synthetic"
        for r in messages_store.list_messages("gc-1")
    )


def test_message_is_recovered_after_process_cache_clear(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    previous_store = messages_store._persistence_store
    messages_store.configure_persistence(store)
    try:
        created = messages_store.add_user_message(
            "gc-1",
            CreateMessageRequest.model_validate({"content": "重启后仍可读取"}),
        )
        messages_store._messages.clear()

        recovered = messages_store.list_messages("gc-1")

        assert [message.id for message in recovered] == [created.id]
        assert recovered[0].content == "重启后仍可读取"
    finally:
        messages_store.reset_messages()
        messages_store.configure_persistence(previous_store)
        store.close()


def test_persistent_message_list_preserves_user_message_api_semantics(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    previous_store = messages_store._persistence_store
    messages_store.configure_persistence(store)
    try:
        from app.storage.repositories import MessageRepository

        MessageRepository(store).append(
            {
                "message_id": "gc-1:msg-1",
                "group_chat_id": "gc-1",
                "sender_type": "system",
                "content": "课题组已创建",
                "mention": None,
                "data_space": "synthetic",
                "created_at": 1.0,
            }
        )
        created = messages_store.add_user_message(
            "gc-1", CreateMessageRequest.model_validate({"content": "用户消息"})
        )

        recovered = messages_store.list_messages("gc-1")

        assert [message.id for message in recovered] == [created.id]
    finally:
        messages_store.reset_messages()
        messages_store.configure_persistence(previous_store)
        store.close()


def test_store_imports_no_forbidden_execution_modules() -> None:
    """消息 store 不导入 LLM、HTTP 或 Memory 执行模块。"""
    import inspect

    source = inspect.getsource(messages_store)
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert len(import_lines) >= 1  # 确有导入（schemas），避免空检查
    for forbidden in ("MemoryTimeline", "app.llm", "httpx", "pathlib", "os."):
        assert not any(forbidden in line for line in import_lines), forbidden


# ---------------- Task 14：消息 API 路由 ----------------

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _create_group_chat_id() -> str:
    response = client.post(
        "/group-chats",
        json={
            "topic_name": "消息 API 测试课题组",
            "topic_summary": "消息 API 测试。",
            "data_space": "synthetic",
            "member_selection": {
                "postdoc": {"selection_mode": "generate", "count": 1},
                "phd_student": {"selection_mode": "generate", "count": 1},
                "master_student": {"selection_mode": "generate", "count": 3},
            },
        },
    )
    assert response.status_code == 200
    return response.json()["group_chat"]["id"]


def test_post_message_creates_user_message() -> None:
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/messages",
        json={"content": "帮我分析强度下降机制", "mention": {"target_type": "all", "target_id": "all", "label": "全体成员"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("msg-")
    assert body["group_chat_id"] == group_chat_id
    assert body["sender_type"] == "user"
    assert body["content"] == "帮我分析强度下降机制"
    assert body["mention"]["target_type"] == "all"
    assert body["data_space"] == "synthetic"


def test_get_messages_returns_in_order() -> None:
    group_chat_id = _create_group_chat_id()
    for content in ("第一条", "第二条", "第三条"):
        response = client.post(
            f"/group-chats/{group_chat_id}/messages", json={"content": content}
        )
        assert response.status_code == 200
    body = client.get(f"/group-chats/{group_chat_id}/messages").json()
    assert [m["content"] for m in body] == ["第一条", "第二条", "第三条"]


def test_messages_unknown_group_chat_404() -> None:
    post = client.post("/group-chats/gc-nope/messages", json={"content": "hi"})
    assert post.status_code == 404
    get = client.get("/group-chats/gc-nope/messages")
    assert get.status_code == 404


def test_messages_empty_content_422() -> None:
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/messages", json={"content": "   "}
    )
    assert response.status_code == 422


def test_post_message_does_not_start_run(monkeypatch) -> None:
    """消息 API 不启动 run（run_store.create 不应被调用）。"""
    from app.api import runs as runs_api

    def boom(*args, **kwargs):
        raise AssertionError("消息 API 不应启动 run")

    monkeypatch.setattr(runs_api.run_store, "create", boom)
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/messages", json={"content": "hi"}
    )
    assert response.status_code == 200
    assert "run_id" not in response.json()
    assert "memory" not in response.json()
