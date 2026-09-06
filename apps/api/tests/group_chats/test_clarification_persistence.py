"""Runtime-driven clarification behavior and durable history."""

import asyncio
import itertools
from types import SimpleNamespace

import pytest

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentResult, RuntimeSelection
from app.agents import service as agents_service
from app.domain.schemas import AgentProfile, DataSpace
from app.group_chats import messages
from app.group_chats.messages import (
    answer_task_clarification,
    create_formal_task,
    create_task_clarification,
    list_clarifications,
    reset_messages,
)
from app.group_chats.schemas import (
    TaskClarificationAnswerRequest,
    DatasetVersionRef,
    TaskClarificationRequest,
)


def _mention(target_type: str = "all") -> dict[str, str]:
    return {"target_type": target_type, "target_id": "all", "label": "全体成员"}


def _record() -> tuple[SimpleNamespace, dict]:
    profile = AgentProfile(
        agent_id="agent-phd-1",
        name="博士 Agent",
        role="phd_student",
        primary_ability="质量审查",
    )
    member = SimpleNamespace(
        id="gc-1:phd_student:agent-phd-1",
        display_name=profile.name,
        role=profile.role,
        status="active",
        selection_mode="existing",
        agent_profile_ref=SimpleNamespace(object_id="demo:agent_profile:agent-phd-1"),
    )
    record = SimpleNamespace(
        members=[member],
        group_chat=SimpleNamespace(data_space=DataSpace.DESENSITIZED_REAL),
        topic=SimpleNamespace(
            topic_name="泡沫混凝土孔结构课题",
            topic_summary="泡沫混凝土孔结构课题摘要",
        ),
    )
    persisted = {
        "agent_id": profile.agent_id,
        "profile": profile.model_dump(mode="json"),
        "enabled": True,
    }
    return record, persisted


def _runtime_result(invocation):
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content="请明确控制变量和可推翻条件。",
        structured_output={
            "question": "请明确控制变量和可推翻条件。",
            "question_id": f"runtime-{invocation.phase}-{invocation.context['question_number']}",
            "reasoning_summary": "需要区分目标、约束和验收标准。",
        },
        data_space=invocation.data_space,
    )


def _patch_runtime(monkeypatch, runtime) -> None:
    record, persisted = _record()
    profile = AgentProfile.model_validate(persisted["profile"])
    monkeypatch.setattr(messages, "get_created_group_chat", lambda _id: record)
    monkeypatch.setattr(
        agents_service,
        "get_agent_record",
        lambda _id: persisted,
    )
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
        lambda _group_chat_id, _mention: (profile, DataSpace.DESENSITIZED_REAL),
    )


def test_each_clarification_turn_uses_real_agent_and_full_history(monkeypatch) -> None:
    reset_messages()
    runtime = MockRuntime(result_factory=_runtime_result)
    _patch_runtime(monkeypatch, runtime)

    clarification = create_task_clarification(
        "gc-1",
        TaskClarificationRequest(
            initial_intent="解释抗压强度下降",
            mention=_mention(),
            source_message_id="msg-intent",
        ),
    )
    answer_task_clarification(
        "gc-1",
        clarification.id,
        TaskClarificationAnswerRequest(answer="样品孔径增大，必须控制湿密度"),
    )

    assert [invocation.agent_id for invocation in runtime.invocations] == [
        "agent-phd-1",
        "agent-phd-1",
    ]
    assert runtime.invocations[0].agent_instruction is not None
    assert runtime.invocations[1].context["initial_intent"] == "解释抗压强度下降"
    assert runtime.invocations[1].context["turns"][0]["answer"] == "样品孔径增大，必须控制湿密度"
    assert runtime.invocations[1].context["question_number"] == 2
    timeline = messages.list_messages("gc-1")
    assert [item.kind for item in timeline] == [
        "clarification_question",
        "clarification_question",
    ]
    assert timeline[0].reply_to_message_id == "msg-intent"


def test_new_clarification_id_does_not_collide_after_process_restart(
    tmp_path, monkeypatch
) -> None:
    store = messages.SQLiteStore(tmp_path / "clarification-restart.db")
    store.initialize()
    previous_store = messages._persistence_store
    messages.configure_persistence(store)
    _patch_runtime(monkeypatch, MockRuntime(result_factory=_runtime_result))
    monkeypatch.setattr(messages, "_seq", itertools.count(1))

    try:
        first = create_task_clarification(
            "gc-1",
            TaskClarificationRequest(
                initial_intent="第一次分析抗压强度下降",
                mention=_mention(),
            ),
        )

        messages._messages.clear()
        messages._clarifications.clear()
        messages._clarification_context.clear()
        messages._formal_tasks.clear()
        monkeypatch.setattr(messages, "_seq", itertools.count(1))

        second = create_task_clarification(
            "gc-1",
            TaskClarificationRequest(
                initial_intent="重启后再次分析抗压强度下降",
                mention=_mention(),
            ),
        )

        persisted = messages._clarification_repository.list_for_group("gc-1")
        assert second.id != first.id
        assert [item["clarification_id"] for item in persisted] == [first.id, second.id]
    finally:
        reset_messages()
        messages.configure_persistence(previous_store)
        store.close()


def test_clarification_runtime_failure_is_persisted_without_local_question(monkeypatch) -> None:
    reset_messages()
    _patch_runtime(monkeypatch, None)

    response = create_task_clarification(
        "gc-1",
        TaskClarificationRequest(
            initial_intent="解释抗压强度下降",
            mention=_mention(),
        ),
    )

    assert response.status == "blocked"
    assert response.question is None
    assert response.question_id is None
    assert response.error_code == "runtime_failed"
    assert list_clarifications("gc-1")[0].status == "blocked"
    projection = messages.list_messages("gc-1")[-1]
    assert projection.kind == "clarification_blocked"
    assert "Runtime" not in projection.content


def test_failed_clarification_has_no_template_question(monkeypatch) -> None:
    reset_messages()
    _patch_runtime(monkeypatch, None)
    response = create_task_clarification(
        "gc-1",
        TaskClarificationRequest(
            initial_intent="实验设计",
            mention=_mention(),
        ),
    )
    assert "围绕" not in (response.question or "")


def test_ready_clarification_projects_a_startable_agent_message(monkeypatch) -> None:
    reset_messages()
    runtime = MockRuntime(result_factory=_runtime_result)
    _patch_runtime(monkeypatch, runtime)

    clarification = create_task_clarification(
        "gc-1",
        TaskClarificationRequest(
            initial_intent="判断抗压强度变化原因",
            mention=_mention(),
            source_message_id="msg-intent",
        ),
    )
    response = answer_task_clarification(
        "gc-1",
        clarification.id,
        TaskClarificationAnswerRequest(
            answer="需要控制湿密度，并交付实验建议报告。",
            source_message_id="msg-answer",
        ),
    )

    assert response.status == "ready_to_assign"
    projection = messages.list_messages("gc-1")[-1]
    assert projection.kind == "clarification_ready"
    assert projection.reply_to_message_id == "msg-answer"
    assert projection.payload == {"clarification_id": clarification.id}


def test_formal_task_rehydrates_topic_context_after_persistence(monkeypatch) -> None:
    """Formal task creation remains valid after the process cache is gone."""
    reset_messages()
    runtime = MockRuntime(result_factory=_runtime_result)
    _patch_runtime(monkeypatch, runtime)
    persisted_records: dict[str, dict] = {}

    class ClarificationRepositoryDouble:
        def create(self, record: dict) -> None:
            persisted_records[record["clarification_id"]] = dict(record)

        def update(self, clarification_id: str, record: dict) -> None:
            persisted_records[clarification_id] = dict(record)

        def get(self, clarification_id: str) -> dict | None:
            return persisted_records.get(clarification_id)

    monkeypatch.setattr(
        messages, "_clarification_repository", ClarificationRepositoryDouble()
    )

    response = create_task_clarification(
        "gc-1",
        TaskClarificationRequest(
            initial_intent="解释抗压强度下降",
            mention=_mention(),
        ),
    )
    context = messages._clarification_context[response.id]
    ready = response.model_copy(
        update={"status": "ready_to_assign", "question": None, "question_id": None}
    )
    messages._save_clarification(ready, context)
    messages._clarification_context.clear()

    formal = create_formal_task("gc-1", response.id)

    assert formal.topic_name == "泡沫混凝土孔结构课题"
    assert formal.topic_summary == "泡沫混凝土孔结构课题摘要"


def test_clarification_persists_browser_dataset_refs(monkeypatch) -> None:
    """JSON-shaped dataset refs from the browser survive clarification persistence."""
    reset_messages()
    runtime = MockRuntime(result_factory=_runtime_result)
    _patch_runtime(monkeypatch, runtime)
    persisted_records: dict[str, dict] = {}

    class ClarificationRepositoryDouble:
        def create(self, record: dict) -> None:
            persisted_records[record["clarification_id"]] = dict(record)

        def update(self, clarification_id: str, record: dict) -> None:
            persisted_records[clarification_id] = dict(record)

        def get(self, clarification_id: str) -> dict | None:
            return persisted_records.get(clarification_id)

    monkeypatch.setattr(messages, "_clarification_repository", ClarificationRepositoryDouble())
    monkeypatch.setattr(
        messages,
        "_dataset_repository",
        SimpleNamespace(
            get=lambda _dataset_id, _version: SimpleNamespace(
                dataset_id="dataset-1",
                version=2,
                group_chat_id="gc-1",
                data_space=DataSpace.DESENSITIZED_REAL,
            )
        ),
        raising=False,
    )

    response = create_task_clarification(
        "gc-1",
        TaskClarificationRequest(
            initial_intent="比较实验版本的强度变化",
            mention=_mention(),
            dataset_refs=[DatasetVersionRef(dataset_id="dataset-1", version=2)],
        ),
    )

    assert persisted_records[response.id]["dataset_refs"] == [
        {"dataset_id": "dataset-1", "version": 2}
    ]


def test_clarification_rejects_dataset_refs_from_another_group(monkeypatch) -> None:
    class DatasetRepositoryDouble:
        def get(self, _dataset_id: str, _version: int):
            return SimpleNamespace(
                group_chat_id="other-group",
                data_space=DataSpace.DESENSITIZED_REAL,
            )

    monkeypatch.setattr(messages, "_dataset_repository", DatasetRepositoryDouble(), raising=False)
    with pytest.raises(messages.ClarificationReadinessError):
        messages._validate_dataset_refs(
            "gc-1",
            [DatasetVersionRef(dataset_id="dataset-1", version=2)],
            DataSpace.DESENSITIZED_REAL,
        )
