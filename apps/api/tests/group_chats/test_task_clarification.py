"""任务澄清 DTO 与 store 测试（tasks.md Task 15）。"""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentResult, RuntimeSelection
from app.agents import service as agents_service
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentRecord
from app.domain.schemas import AgentProfile, AgentRole, DataSpace
from app.group_chats import messages
from app.group_chats.messages import (
    ClarificationClosedError,
    GroupChatMemberNotFoundError,
    GroupChatMissingPhDError,
    answer_task_clarification,
    create_task_clarification,
    list_clarifications,
    reset_messages,
)
from app.group_chats.schemas import (
    TaskClarificationAnswerRequest,
    TaskClarificationRequest,
    TaskClarificationResponse,
)


_REAL_READINESS = messages.resolve_clarification_readiness


@pytest.fixture(autouse=True)
def _reset():
    reset_messages()
    yield
    reset_messages()


def _mention(target_type: str = "all", target_id: str = "all", label: str = "全体成员") -> dict:
    return {"target_type": target_type, "target_id": target_id, "label": label}


def _clarification_result(invocation):
    prior = invocation.context.get("turns", [])
    focus = (
        prior[-1]["answer"]
        if prior
        else invocation.context.get("initial_intent", "当前任务")
    )
    question = f"请基于{focus}明确控制变量、判别证据和交付物？"
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=question,
        structured_output={
            "question": question,
            "question_id": f"question-{invocation.context['question_number']}",
        },
        data_space=invocation.data_space,
    )


@pytest.fixture(autouse=True)
def _runtime(monkeypatch):
    runtime = MockRuntime(result_factory=_clarification_result)
    monkeypatch.setattr(
        messages,
        "resolve_runtime_policy",
        lambda *args, **kwargs: RuntimeSelection(
            api_mode="live", resolved_mode="live", runtime_name="mock"
        ),
    )
    monkeypatch.setattr(messages, "create_runtime", lambda *args, **kwargs: runtime)
    monkeypatch.setattr(
        messages,
        "resolve_clarification_readiness",
        lambda group_chat_id, mention: (
            messages._resolve_clarifier_agent(group_chat_id, mention)[1],
            DataSpace.SYNTHETIC,
        ),
    )


# ---------------- DTO ----------------

def test_task_clarification_request_requires_intent_and_mention() -> None:
    request = TaskClarificationRequest.model_validate(
        {
            "initial_intent": "请帮我分析高掺量泥浆导致强度下降的机制",
            "mention": _mention(),
        }
    )
    assert request.initial_intent.startswith("请帮我分析")
    assert request.mention.target_type == "all"


def test_task_clarification_requests_preserve_the_triggering_message_id() -> None:
    request = TaskClarificationRequest.model_validate(
        {
            "initial_intent": "请帮我分析高掺量泥浆导致强度下降的机制",
            "mention": _mention(),
            "source_message_id": "msg-user-1",
        }
    )
    answer = TaskClarificationAnswerRequest.model_validate(
        {"answer": "重点比较孔结构", "source_message_id": "msg-user-2"}
    )

    assert request.source_message_id == "msg-user-1"
    assert answer.source_message_id == "msg-user-2"


def test_task_clarification_request_preserves_dataset_version_selection() -> None:
    request = TaskClarificationRequest.model_validate(
        {
            "initial_intent": "比较不同实验版本的强度变化",
            "mention": _mention(),
            "dataset_refs": [
                {"dataset_id": "dataset-a", "version": 2},
                {"dataset_id": "dataset-b", "version": 1},
            ],
        }
    )

    assert [ref.model_dump() for ref in request.dataset_refs] == [
        {"dataset_id": "dataset-a", "version": 2},
        {"dataset_id": "dataset-b", "version": 1},
    ]


def test_task_clarification_request_blank_intent_422() -> None:
    with pytest.raises(ValidationError):
        TaskClarificationRequest.model_validate(
            {"initial_intent": "  ", "mention": _mention()}
        )


def test_task_clarification_request_missing_mention_422() -> None:
    with pytest.raises(ValidationError):
        TaskClarificationRequest.model_validate({"initial_intent": "x"})


def test_task_clarification_response_defaults() -> None:
    response = TaskClarificationResponse.model_validate(
        {
            "id": "clarification-1",
            "group_chat_id": "gc-1",
            "clarifier": "博士 Agent",
            "question_id": "question-1",
            "question": "q1",
            "question_number": 1,
            "max_questions": 7,
            "turns": [],
        }
    )
    assert response.status == "awaiting_answer"
    assert response.data_space.value == "synthetic"


def test_task_clarification_response_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        TaskClarificationResponse.model_validate(
            {
                "id": "c1",
                "group_chat_id": "gc-1",
                "status": "done",
                "clarifier": "博士 Agent",
                "question_id": "question-1",
                "question": "q1",
                "question_number": 1,
                "max_questions": 7,
                "turns": [],
            }
        )


def test_blocked_clarification_exposes_safe_readiness_copy() -> None:
    response = TaskClarificationResponse.model_validate(
        {
            "id": "clarification-1",
            "group_chat_id": "gc-1",
            "status": "blocked",
            "clarifier": "博士 Agent",
            "question_number": 1,
            "error_code": "agent_not_ready",
            "user_message": "该 Agent 暂未完成运行配置，请先完成配置后再 @ 它。",
            "data_space": "desensitized_real",
        }
    )

    assert response.error_code == "agent_not_ready"
    assert "Traceback" not in response.user_message


# ---------------- store：澄清者解析 ----------------

def _create_group_chat_id() -> str:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/group-chats",
        json={
            "topic_name": "任务澄清测试课题组",
            "topic_summary": "任务澄清测试。",
            "member_selection": {
            "postdoc": {"selection_mode": "existing", "agent_ids": ["agent-postdoc-1"]},
            "phd_student": {"selection_mode": "existing", "agent_ids": ["agent-phd-1"]},
            "master_student": {"selection_mode": "existing", "agent_ids": ["agent-ms-1", "agent-ms-2", "agent-ms-3"]},
            },
        },
    )
    assert response.status_code == 200
    return response.json()["group_chat"]["id"]


def _live_group(member_status: str = "active") -> SimpleNamespace:
    return SimpleNamespace(
        group_chat=SimpleNamespace(data_space=DataSpace.DESENSITIZED_REAL),
        topic=SimpleNamespace(topic_name="真实科研课题", topic_summary="基于已上传证据分析强度变化"),
        members=[
            SimpleNamespace(
                id="gc-live:phd_student:agent-live-phd",
                role=AgentRole.PHD_STUDENT,
                status=member_status,
                agent_profile_ref=SimpleNamespace(object_id="agent:agent-live-phd"),
            )
        ],
    )


def _live_agent_record() -> dict:
    profile = AgentProfile(
        agent_id="agent-live-phd",
        name="资料分析博士",
        role=AgentRole.PHD_STUDENT,
        primary_ability="资料分析",
        allowed_data_spaces=[DataSpace.DESENSITIZED_REAL],
        allowed_tools=["knowledge.search"],
    )
    return {
        "agent_id": profile.agent_id,
        "enabled": True,
        "profile": profile.model_dump(mode="json"),
    }


def _save_ready_document(store) -> None:
    DocumentRepository(store).save(
        DocumentRecord(
            document_id="doc-ready-1",
            group_chat_id="gc-live",
            filename="evidence.txt",
            mime_type="text/plain",
            size_bytes=8,
            sha256="a" * 64,
            storage_key="gc-live/doc-ready-1.txt",
            data_space="desensitized_real",
            status="ready",
            created_at=1.0,
            updated_at=1.0,
        )
    )


def test_clarification_invocation_uses_its_real_group_space(tmp_path, monkeypatch) -> None:
    store = messages.SQLiteStore(tmp_path / "clarification.db")
    store.initialize()
    previous_store = messages._persistence_store
    messages.configure_persistence(store)
    _save_ready_document(store)
    captured = []

    class CapturingRuntime:
        async def invoke(self, invocation):
            captured.append(invocation)
            return _clarification_result(invocation)

    monkeypatch.setattr(messages, "get_created_group_chat", lambda _group_id: _live_group())
    monkeypatch.setattr(messages, "resolve_clarification_readiness", _REAL_READINESS)
    monkeypatch.setattr(
        agents_service,
        "get_agent_record",
        lambda agent_id: _live_agent_record() if agent_id == "agent-live-phd" else None,
    )
    monkeypatch.setattr(messages, "create_runtime", lambda _selection: CapturingRuntime())
    try:
        response = create_task_clarification(
            "gc-live",
            TaskClarificationRequest.model_validate(
                {
                    "initial_intent": "分析强度变化的证据",
                    "mention": _mention("all"),
                }
            ),
        )
        follow_up = answer_task_clarification(
            "gc-live",
            response.id,
            TaskClarificationAnswerRequest(
                answer="重点比较孔结构与抗压强度的对应关系",
                source_message_id="msg-user-2",
            ),
        )
    finally:
        messages.reset_messages()
        messages.configure_persistence(previous_store)
        store.close()

    assert response.status == "awaiting_answer"
    assert captured[0].data_space == "desensitized_real"
    clarification_scope = response.id
    assert captured[0].run_id == clarification_scope
    assert captured[0].task_id == clarification_scope
    assert captured[0].allowed_tools == []
    assert captured[0].agent_instruction.allowed_tools == []
    assert follow_up.status == "awaiting_answer"
    assert captured[1].data_space == "desensitized_real"
    assert captured[1].run_id == clarification_scope
    assert captured[1].task_id == clarification_scope


def test_runtime_protocol_failure_is_not_reported_as_provider_outage(monkeypatch) -> None:
    runtime = MockRuntime(
        result_factory=lambda invocation: AgentResult(
            agent_id=invocation.agent_id,
            status="error",
            content="",
            error="native Pi rejected request: HTTP 400",
            error_code="pi_protocol",
            data_space=invocation.data_space,
        )
    )
    monkeypatch.setattr(messages, "create_runtime", lambda _selection: runtime)

    group_chat_id = _create_group_chat_id()
    response = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "分析强度变化的证据", "mention": _mention("all")}
        ),
    )

    assert response.status == "blocked"
    assert response.error_code == "runtime_protocol"
    assert "运行协议" in response.user_message
    assert "暂时不可用" not in response.user_message


def test_unconfigured_mention_returns_blocked_postdoc_copy(monkeypatch) -> None:
    monkeypatch.setattr(
        messages,
        "get_created_group_chat",
        lambda _group_id: _live_group(member_status="pending_generation"),
    )
    monkeypatch.setattr(messages, "resolve_clarification_readiness", _REAL_READINESS)

    response = create_task_clarification(
        "gc-live",
        TaskClarificationRequest.model_validate(
            {"initial_intent": "分析强度变化的证据", "mention": _mention("all")}
        ),
    )

    assert response.status == "blocked"
    assert response.error_code == "agent_not_ready"
    assert "暂未完成运行配置" in response.user_message
    assert "Traceback" not in response.user_message


def test_create_task_clarification_all_uses_phd_clarifier() -> None:
    group_chat_id = _create_group_chat_id()
    response = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "分析强度下降机制", "mention": _mention("all")}
        ),
    )
    assert response.clarifier == "演示博士生 Agent"
    assert response.group_chat_id == group_chat_id
    assert response.status == "awaiting_answer"
    assert response.data_space.value == "synthetic"
    assert response.question_id
    assert response.question
    assert response.question_number == 1
    assert response.max_questions == 7
    assert response.turns == []


def test_create_task_clarification_member_uses_member_label() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    create_body = client.post(
        "/group-chats",
        json={
            "topic_name": "成员澄清测试",
            "topic_summary": "x",
            "member_selection": {
                "postdoc": {"selection_mode": "existing", "agent_ids": ["agent-postdoc-1"]},
                "phd_student": {"selection_mode": "existing", "agent_ids": ["agent-phd-1"]},
                "master_student": {"selection_mode": "existing", "agent_ids": ["agent-ms-1", "agent-ms-2", "agent-ms-3"]},
            },
        },
    ).json()
    group_chat_id = create_body["group_chat"]["id"]
    master = next(
        m for m in create_body["members"] if m["role"] == "master_student"
    )
    response = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {
                "initial_intent": "整理文献",
                "mention": _mention("member", target_id=master["id"], label=master["display_name"]),
            }
        ),
    )
    assert response.clarifier == master["display_name"]


def test_create_task_clarification_role_uses_role_representative() -> None:
    group_chat_id = _create_group_chat_id()
    response = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {
                "initial_intent": "实验设计",
                "mention": _mention("role", target_id="role:master_student", label="硕士"),
            }
        ),
    )
    assert response.clarifier == "演示硕士生 Agent"


def test_create_task_clarification_member_not_in_group_raises() -> None:
    group_chat_id = _create_group_chat_id()
    with pytest.raises(GroupChatMemberNotFoundError):
        create_task_clarification(
            group_chat_id,
            TaskClarificationRequest.model_validate(
                {
                    "initial_intent": "x",
                    "mention": _mention("member", target_id="gc-other:master_student:agent-x", label="外人"),
                }
            ),
        )


def test_create_task_clarification_all_without_phd_raises() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    create_body = client.post(
        "/group-chats",
        json={
            "topic_name": "无博士测试",
            "topic_summary": "x",
            "member_selection": {
                "postdoc": {"selection_mode": "generate", "count": 1},
                "phd_student": {"selection_mode": "generate", "count": 0},
                "master_student": {"selection_mode": "generate", "count": 3},
            },
        },
    )
    # 后端成员结构校验：博士至少 1 人，创建本身就会 422
    assert create_body.status_code == 422


def test_create_task_clarification_returns_one_current_question() -> None:
    group_chat_id = _create_group_chat_id()
    response = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "x", "mention": _mention("all")}
        ),
    )
    assert response.question
    assert response.question_id
    assert response.question_number == 1
    assert response.max_questions == 7


def test_clarifications_are_recorded_in_order() -> None:
    group_chat_id = _create_group_chat_id()
    first = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "任务一", "mention": _mention("all")}
        ),
    )
    second = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "任务二", "mention": _mention("all")}
        ),
    )
    records = list_clarifications(group_chat_id)
    assert [r.id for r in records] == [first.id, second.id]
    assert [r.clarifier for r in records] == ["演示博士生 Agent", "演示博士生 Agent"]


def test_answer_task_clarification_generates_next_question_from_history() -> None:
    group_chat_id = _create_group_chat_id()
    first = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "分析孔结构导致抗压强度下降的机制", "mention": _mention("all")}
        ),
    )

    second = answer_task_clarification(
        group_chat_id,
        first.id,
        TaskClarificationAnswerRequest(answer="重点比较孔结构和抗压强度，并控制湿密度"),
    )

    assert second.status == "awaiting_answer"
    assert second.question_number == 2
    assert len(second.turns) == 1
    assert "孔结构" in second.question or "抗压强度" in second.question
    assert second.question != first.question


def test_next_clarification_question_uses_new_answer_context() -> None:
    """下一问必须吸收上一轮新增的材料条件，而不是只复述初始意图。"""
    group_chat_id = _create_group_chat_id()
    first = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "分析强度下降机制", "mention": _mention("all")}
        ),
    )

    second = answer_task_clarification(
        group_chat_id,
        first.id,
        TaskClarificationAnswerRequest(answer="必须控制湿密度，并建立同批样品对应关系"),
    )

    assert "湿密度" in second.question or "样品" in second.question


def test_postdoc_clarification_question_uses_domain_boundary() -> None:
    group_chat_id = _create_group_chat_id()
    response = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {
                "initial_intent": "设计含泡体系孔结构判别实验",
                "mention": _mention("role", "role:postdoc", "博士后"),
            }
        ),
    )
    assert "材料" in response.question or "专业范围" in response.question or "判别" in response.question


def test_seventh_answer_closes_without_eighth_question() -> None:
    group_chat_id = _create_group_chat_id()
    response = create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "记录一个复杂实验任务", "mention": _mention("all")}
        ),
    )
    for index in range(6):
        response = answer_task_clarification(
            group_chat_id,
            response.id,
            TaskClarificationAnswerRequest(answer=f"第 {index + 1} 轮补充信息"),
        )
        assert response.question_number == index + 2

    closed = answer_task_clarification(
        group_chat_id,
        response.id,
        TaskClarificationAnswerRequest(answer="最终交付观点卡和实验建议"),
    )
    assert closed.status == "ready_to_assign"
    assert closed.question is None
    assert closed.question_id is None
    with pytest.raises(ClarificationClosedError):
        answer_task_clarification(
            group_chat_id,
            response.id,
            TaskClarificationAnswerRequest(answer="不应生成第八题"),
        )


def test_reset_messages_clears_clarifications() -> None:
    group_chat_id = _create_group_chat_id()
    create_task_clarification(
        group_chat_id,
        TaskClarificationRequest.model_validate(
            {"initial_intent": "x", "mention": _mention("all")}
        ),
    )
    reset_messages()
    assert list_clarifications(group_chat_id) == []


# ---------------- Task 16：任务澄清 API 路由 ----------------

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_post_task_clarification_all_returns_phd_clarifier() -> None:
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications",
        json={
            "initial_intent": "请帮我分析高掺量泥浆导致强度下降的机制",
            "mention": {"target_type": "all", "target_id": "all", "label": "全体成员"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["clarifier"] == "演示博士生 Agent"
    assert body["status"] == "awaiting_answer"
    assert body["data_space"] == "synthetic"
    assert body["question"]
    assert body["question_id"]
    assert body["question_number"] == 1
    assert body["max_questions"] == 7
    assert body["turns"] == []
    assert "memory" not in body and "run_id" not in body


def test_post_task_clarification_answer_returns_next_question() -> None:
    group_chat_id = _create_group_chat_id()
    created = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications",
        json={
            "initial_intent": "分析孔结构和抗压强度关系",
            "mention": {"target_type": "all", "target_id": "all", "label": "全体成员"},
        },
    )
    clarification_id = created.json()["id"]
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications/{clarification_id}/answers",
        json={"answer": "先控制湿密度，再比较孔结构和抗压强度"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_answer"
    assert body["question_number"] == 2
    assert len(body["turns"]) == 1
    assert "孔结构" in body["question"] or "抗压强度" in body["question"]


def test_post_task_clarification_answer_empty_is_422() -> None:
    group_chat_id = _create_group_chat_id()
    created = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications",
        json={
            "initial_intent": "分析实验",
            "mention": {"target_type": "all", "target_id": "all", "label": "全体成员"},
        },
    )
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications/{created.json()['id']}/answers",
        json={"answer": "  "},
    )
    assert response.status_code == 422


def test_post_task_clarification_answer_unknown_session_is_404() -> None:
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications/clarification-nope/answers",
        json={"answer": "补充信息"},
    )
    assert response.status_code == 404


def test_post_task_clarification_member_returns_member_label() -> None:
    create_body = client.post(
        "/group-chats",
        json={
            "topic_name": "成员澄清 API 测试",
            "topic_summary": "x",
            "member_selection": {
                "postdoc": {"selection_mode": "existing", "agent_ids": ["agent-postdoc-1"]},
                "phd_student": {"selection_mode": "existing", "agent_ids": ["agent-phd-1"]},
                "master_student": {"selection_mode": "existing", "agent_ids": ["agent-ms-1", "agent-ms-2", "agent-ms-3"]},
            },
        },
    ).json()
    group_chat_id = create_body["group_chat"]["id"]
    master = next(m for m in create_body["members"] if m["role"] == "master_student")
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications",
        json={
            "initial_intent": "整理文献",
            "mention": {
                "target_type": "member",
                "target_id": master["id"],
                "label": master["display_name"],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["clarifier"] == master["display_name"]


def test_task_clarification_unknown_group_chat_404() -> None:
    response = client.post(
        "/group-chats/gc-nope/task-clarifications",
        json={
            "initial_intent": "x",
            "mention": {"target_type": "all", "target_id": "all", "label": "全体成员"},
        },
    )
    assert response.status_code == 404


def test_task_clarification_invalid_mention_target_422() -> None:
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications",
        json={
            "initial_intent": "x",
            "mention": {"target_type": "everyone", "target_id": "all", "label": "全体成员"},
        },
    )
    assert response.status_code == 422


def test_task_clarification_member_not_in_group_422() -> None:
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications",
        json={
            "initial_intent": "x",
            "mention": {
                "target_type": "member",
                "target_id": "gc-other:master_student:agent-x",
                "label": "外人",
            },
        },
    )
    assert response.status_code == 422
    assert "成员不属于该课题组" in response.json()["detail"]


def test_task_clarification_does_not_start_run(monkeypatch) -> None:
    """澄清 API 不启动 run（run_store.create 不应被调用）。"""
    from app.api import runs as runs_api

    def boom(*args, **kwargs):
        raise AssertionError("澄清 API 不应启动 run")

    monkeypatch.setattr(runs_api.run_store, "create", boom)
    group_chat_id = _create_group_chat_id()
    response = client.post(
        f"/group-chats/{group_chat_id}/task-clarifications",
        json={
            "initial_intent": "x",
            "mention": {"target_type": "all", "target_id": "all", "label": "全体成员"},
        },
    )
    assert response.status_code == 200
