"""demo-safe 消息与任务澄清服务（design.md §2.4，tasks.md Task 13）。

职责：

- `add_user_message`：保存 demo 阶段用户消息（含可选 `@` mention）。
- `list_messages`：按创建顺序返回消息。
- `reset_messages`：清空消息（demo reset / 测试用）。

边界约定：

- 应用配置 SQLite 时，用户消息写入并可回读；未配置时使用进程内 fallback。
- 所有消息标记 `data_space = synthetic`；不写正式 Memory。
- group chat 存在性校验由 router 层负责（design §7.2：不存在 -> 404）。
- 任务澄清记录（Task 15）也保存在本模块，与消息同属 demo 会话对象。
"""

from __future__ import annotations

import itertools
import asyncio
import time
import uuid
from typing import Literal

from app.agent_runtime.factory import create_runtime
from app.agent_runtime.instruction_builder import build_agent_instruction
from app.agent_runtime.runtime_policy import resolve_runtime_policy
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.agents import service as agents_service
from app.documents.repository import DocumentRepository
from app.domain.schemas import DataSpace
from app.experiments.repository import ExperimentDatasetRepository
from app.group_chats.creation_service import get_created_group_chat
from app.group_chats.schemas import (
    ChatMessageRecord,
    ChatMessageKind,
    ClarificationTurn,
    CreateMessageRequest,
    FormalTaskContext,
    DatasetVersionRef,
    MentionTarget,
    TaskClarificationAnswerRequest,
    TaskClarificationRequest,
    TaskClarificationResponse,
)
from app.group_chats.clarification import (
    MAX_QUESTIONS,
    clarification_is_ready,
)
from app.storage.repositories import (
    ClarificationRepository,
    FormalTaskRepository,
    GroupChatRepository,
    MessageRepository,
)
from app.storage.sqlite_store import SQLiteStore

_seq = itertools.count(1)

_messages: dict[str, list[ChatMessageRecord]] = {}
_clarifications: dict[str, list[TaskClarificationResponse]] = {}
_clarification_context: dict[str, dict] = {}
_formal_tasks: dict[str, dict] = {}
_persistence_store: SQLiteStore | None = None
_message_repository: MessageRepository | None = None
_clarification_repository: ClarificationRepository | None = None
_formal_task_repository: FormalTaskRepository | None = None
_dataset_repository: ExperimentDatasetRepository | None = None


def configure_persistence(store: SQLiteStore | None) -> None:
    """Configure optional durable storage for chat messages."""
    global _persistence_store, _message_repository, _clarification_repository
    global _formal_task_repository, _dataset_repository
    _persistence_store = store
    _message_repository = MessageRepository(store) if store else None
    _clarification_repository = ClarificationRepository(store) if store else None
    _formal_task_repository = FormalTaskRepository(store) if store else None
    _dataset_repository = ExperimentDatasetRepository(store) if store else None


class GroupChatMemberNotFoundError(Exception):
    """mention 成员不属于该课题组（design §7.2 -> 422）。"""


class GroupChatMissingPhDError(Exception):
    """`@全体` 时课题组缺少博士 Agent，无法代表团队澄清（design §7.2 -> 422）。"""


def add_user_message(
    group_chat_id: str, request: CreateMessageRequest
) -> ChatMessageRecord:
    """保存一条用户消息；资料空间始终由服务端课题组记录决定。"""
    return append_chat_message(
        group_chat_id,
        sender_type="user",
        sender_id=request.sender_id,
        content=request.content,
        mention=request.mention,
        task_id=request.task_id,
        attachment_ids=request.attachment_ids,
    )


def _message_data_space(group_chat_id: str) -> DataSpace:
    if _persistence_store is not None:
        persisted = GroupChatRepository(_persistence_store).get(group_chat_id)
        if persisted is not None:
            return DataSpace(persisted["data_space"])
    record = get_created_group_chat(group_chat_id)
    group_space = getattr(getattr(record, "group_chat", None), "data_space", None)
    if isinstance(group_space, DataSpace):
        return group_space
    if isinstance(group_space, str):
        return DataSpace(group_space)
    return DataSpace.SYNTHETIC


def append_chat_message(
    group_chat_id: str,
    *,
    sender_type: Literal["user", "system", "agent"],
    sender_id: str | None = None,
    content: str,
    kind: ChatMessageKind = "text",
    payload: dict[str, object] | None = None,
    mention: MentionTarget | None = None,
    task_id: str | None = None,
    attachment_ids: tuple[str, ...] | list[str] = (),
    reply_to_message_id: str | None = None,
) -> ChatMessageRecord:
    """Append a durable chat fact using the group-owned data space."""
    record = ChatMessageRecord(
        id=f"msg-{time.time_ns()}-{next(_seq)}",
        group_chat_id=group_chat_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        mention=mention,
        task_id=task_id,
        attachment_ids=list(attachment_ids),
        kind=kind,
        payload=dict(payload or {}),
        reply_to_message_id=reply_to_message_id,
        created_at=time.time(),
        data_space=_message_data_space(group_chat_id),
    )
    if _message_repository is not None:
        _message_repository.append(
            {
                "message_id": record.id,
                "group_chat_id": record.group_chat_id,
                "sender_type": record.sender_type,
                "sender_id": record.sender_id,
                "content": record.content,
                "mention": record.mention.model_dump(mode="json")
                if record.mention is not None
                else None,
                "task_id": record.task_id,
                "attachment_ids": record.attachment_ids,
                "kind": record.kind,
                "payload": record.payload,
                "reply_to_message_id": record.reply_to_message_id,
                "data_space": record.data_space.value,
                "created_at": record.created_at,
            }
        )
    _messages.setdefault(group_chat_id, []).append(record)
    return record


def list_messages(group_chat_id: str) -> list[ChatMessageRecord]:
    """按创建顺序返回该群聊的消息；无消息时返回空列表。"""
    if _message_repository is not None:
        return [
            ChatMessageRecord.model_validate(
                {
                    "id": item["message_id"],
                    "group_chat_id": item["group_chat_id"],
                    "sender_type": item["sender_type"],
                    "sender_id": item["sender_id"],
                    "content": item["content"],
                    "mention": item["mention"],
                    "task_id": item["task_id"],
                    "attachment_ids": item["attachment_ids"],
                    "kind": item["kind"],
                    "payload": item["payload"],
                    "reply_to_message_id": item["reply_to_message_id"],
                    "data_space": item["data_space"],
                    "created_at": item["created_at"],
                }
            )
            for item in _message_repository.list(group_chat_id)
            if item["sender_type"] != "system"
        ]
    return list(_messages.get(group_chat_id, []))


def _resolve_clarifier(group_chat_id: str, mention) -> str:
    """解析澄清者（design §5.3）。

    - `all`：博士 Agent 代表团队（课题组必须有博士成员）。
    - `member`：被点名成员（必须属于该课题组）。
    - `role`：该角色代表（按 label 表达）。
        """
    _, profile = _resolve_clarifier_agent(group_chat_id, mention)
    return profile.name


class ClarificationNotFoundError(Exception):
    """澄清会话不存在。"""


class ClarificationClosedError(Exception):
    """澄清会话已经完成，不能提交第八个问题。"""


class ClarificationRuntimeError(Exception):
    """The selected Agent Runtime is unavailable for clarification."""

    def __init__(
        self,
        detail: str,
        *,
        code: str = "runtime_failed",
        user_message: str = "Agent 运行未能完成，请稍后重试。",
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.user_message = user_message


class ClarificationProtocolError(Exception):
    """The Runtime returned a malformed clarification question."""


class ClarificationReadinessError(Exception):
    """A user-actionable prerequisite for Live clarification is missing."""

    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


_RUNTIME_ERROR_COPY: dict[str, tuple[str, str]] = {
    "pi_unavailable": (
        "runtime_unavailable",
        "分析服务暂时无法连接，请稍后重试。",
    ),
    "pi_timeout": (
        "runtime_timeout",
        "分析服务响应超时，请稍后重试。",
    ),
    "pi_auth": (
        "runtime_auth",
        "分析服务鉴权失败，请联系管理员检查运行配置。",
    ),
    "pi_protocol": (
        "runtime_protocol",
        "分析请求未通过运行协议校验，请联系管理员检查服务版本。",
    ),
}


def _runtime_failure(error_code: str, detail: str) -> ClarificationRuntimeError:
    code, user_message = _RUNTIME_ERROR_COPY.get(
        error_code,
        ("runtime_failed", "Agent 运行未能完成，请稍后重试。"),
    )
    return ClarificationRuntimeError(detail, code=code, user_message=user_message)


def _group_data_space(group_chat_id: str) -> DataSpace:
    record = get_created_group_chat(group_chat_id)
    group_space = getattr(getattr(record, "group_chat", None), "data_space", None)
    if group_space not in {DataSpace.REAL, DataSpace.DESENSITIZED_REAL}:
        raise ClarificationReadinessError(
            "group_not_live_ready",
            "当前课题组尚未准备好进行真实资料分析，请重新创建或检查课题组配置。",
        )
    return group_space


def _validate_dataset_refs(
    group_chat_id: str,
    refs: list[DatasetVersionRef],
    group_space: DataSpace,
) -> list[DatasetVersionRef]:
    if not refs:
        return []
    if _dataset_repository is None:
        raise ClarificationReadinessError(
            "dataset_not_ready",
            "所选实验数据版本暂不可用，请重新打开实验数据工作区后重试。",
        )
    validated: list[DatasetVersionRef] = []
    for ref in refs:
        dataset = _dataset_repository.get(ref.dataset_id, ref.version)
        if dataset is None:
            raise ClarificationReadinessError(
                "dataset_not_found",
                f"所选实验数据版本不存在：{ref.dataset_id} v{ref.version}。",
            )
        dataset_space = str(getattr(dataset.data_space, "value", dataset.data_space))
        if dataset.group_chat_id != group_chat_id:
            raise ClarificationReadinessError(
                "dataset_scope_denied",
                "所选实验数据版本不属于当前课题组。",
            )
        if dataset_space != group_space.value:
            raise ClarificationReadinessError(
                "dataset_data_space_denied",
                "所选实验数据版本与当前课题组资料空间不一致。",
            )
        validated.append(DatasetVersionRef(dataset_id=dataset.dataset_id, version=dataset.version))
    return validated


def resolve_clarification_readiness(
    group_chat_id: str, mention: MentionTarget
) -> tuple[object, DataSpace]:
    """Resolve the only Agent and scope allowed to ask a Live question."""
    group_space = _group_data_space(group_chat_id)
    try:
        _, profile = _resolve_clarifier_agent(group_chat_id, mention)
    except ClarificationRuntimeError as exc:
        raise ClarificationReadinessError(
            "agent_not_ready",
            "该 Agent 暂未完成运行配置，请先完成配置后再 @ 它。",
        ) from exc

    if group_space not in profile.allowed_data_spaces:
        raise ClarificationReadinessError(
            "agent_data_space_denied",
            "该 Agent 无权访问当前课题组资料，请更换已授权成员。",
        )
    if "knowledge.search" not in profile.allowed_tools:
        raise ClarificationReadinessError(
            "agent_not_ready",
            "该 Agent 暂未完成运行配置，请先完成配置后再 @ 它。",
        )
    if _persistence_store is None or not any(
        document.status == "ready"
        for document in DocumentRepository(_persistence_store).list_for_group(group_chat_id)
    ):
        raise ClarificationReadinessError(
            "documents_not_ready",
            "请先上传并完成至少一份科研资料的解析，再分配研究任务。",
        )
    selection = resolve_runtime_policy("live", require_pi=True)
    if selection.runtime_name == "unavailable":
        raise ClarificationReadinessError(
            "provider_unavailable",
            "分析服务暂未完成运行配置，请稍后重试或联系管理员。",
        )
    return profile, group_space


def _blocked_response(
    *,
    clarification_id: str,
    group_chat_id: str,
    group_space: DataSpace,
    error: ClarificationReadinessError,
    question_number: int,
    turns: list[ClarificationTurn],
    clarifier: str = "博士后",
    dataset_refs: list[DatasetVersionRef] | None = None,
) -> TaskClarificationResponse:
    return TaskClarificationResponse(
        id=clarification_id,
        group_chat_id=group_chat_id,
        status="blocked",
        clarifier=clarifier,
        question_id=None,
        question=None,
        question_number=question_number,
        max_questions=MAX_QUESTIONS,
        turns=turns,
        error_code=error.code,
        user_message=error.user_message,
        data_space=group_space,
        dataset_refs=list(dataset_refs or []),
    )


def _agent_id_from_member(member) -> str:
    reference = getattr(member, "agent_profile_ref", None)
    object_id = str(getattr(reference, "object_id", ""))
    return object_id.rsplit(":", 1)[-1] if object_id else ""


def _resolve_clarifier_agent(group_chat_id: str, mention):
    record = get_created_group_chat(group_chat_id)
    members = record.members if record is not None else []
    if mention.target_type == "member":
        candidates = [member for member in members if member.id == mention.target_id]
        if not candidates:
            raise GroupChatMemberNotFoundError(
                f"成员不属于该课题组: {mention.target_id!r}"
            )
    elif mention.target_type == "all":
        candidates = [
            member
            for member in members
            if getattr(member.role, "value", member.role) == "phd_student"
        ]
        if not candidates:
            raise GroupChatMissingPhDError("缺少博士 Agent，无法代表团队澄清")
    else:
        role_key = mention.target_id.removeprefix("role:")
        candidates = [
            member
            for member in members
            if getattr(member.role, "value", member.role) == role_key
        ]
        if not candidates:
            raise GroupChatMemberNotFoundError(f"课题组没有可用的{mention.label} Agent")

    for member in candidates:
        agent_id = _agent_id_from_member(member)
        if getattr(member, "status", "") != "active" or not agent_id:
            continue
        record = agents_service.get_agent_record(agent_id)
        if record is None:
            continue
        if not record.get("enabled", False):
            raise ClarificationRuntimeError(f"Agent 已停用，不能生成澄清问题: {agent_id}")
        from app.domain.schemas import AgentProfile

        profile = AgentProfile.model_validate(record["profile"])
        expected_role = getattr(member.role, "value", member.role)
        actual_role = getattr(profile.role, "value", profile.role)
        if actual_role != expected_role:
            raise GroupChatMemberNotFoundError(f"Agent 角色不匹配: {agent_id}")
        return member, profile
    raise ClarificationRuntimeError("该成员尚未配置为可执行 Agent")


def _invoke_question(
    *,
    clarification_id: str,
    group_chat_id: str,
    profile,
    topic_name: str,
    topic_summary: str,
    initial_intent: str,
    turns: list[ClarificationTurn],
    question_number: int,
    data_space: DataSpace,
) -> tuple[str, str]:
    if question_number < 1 or question_number > MAX_QUESTIONS:
        raise ClarificationProtocolError("澄清问题轮次超出最大问题数")
    selection = resolve_runtime_policy("live", require_pi=True)
    if selection.runtime_name == "unavailable":
        raise ClarificationRuntimeError(
            selection.fallback_reason or "Agent Runtime 不可用"
        )
    runtime = create_runtime(selection)
    if runtime is None:
        raise ClarificationRuntimeError("Agent Runtime 不可用")
    topic_context = {"name": topic_name, "summary": topic_summary}
    task_context = {
        "group_chat_id": group_chat_id,
        "topic_name": topic_name,
        "topic_summary": topic_summary,
        "initial_intent": initial_intent,
        "mention": profile.agent_id,
        "turns": [turn.model_dump(mode="json") for turn in turns],
        "question_number": question_number,
        "max_questions": MAX_QUESTIONS,
    }
    instruction = build_agent_instruction(
        profile,
        profile_version="current",
        topic_context=topic_context,
        task_context=task_context,
        phase="task_clarification",
        output_contract="clarification_question",
    )
    instruction = instruction.model_copy(update={"allowed_tools": []})
    clarification_scope = clarification_id
    invocation = AgentInvocation(
        run_id=clarification_scope,
        group_chat_id=group_chat_id,
        phase="task_clarification",
        agent_id=profile.agent_id,
        role=profile.role.value,
        profile_version="current",
        agent_instruction=instruction,
        task=(
            "基于完整课题上下文和历史问答，提出下一条苏格拉底式澄清问题。"
            "只提出一个问题，不替用户作出科研结论。"
        ),
        context=task_context,
        allowed_tools=[],
        output_contract="clarification_question",
        data_space=data_space.value,
        task_id=clarification_scope,
        safety_rules=["no_formal_memory_write", "no_stage_transition"],
    )
    try:
        result = asyncio.run(runtime.invoke(invocation))
    except Exception as exc:
        raise ClarificationRuntimeError(f"Agent Runtime 调用失败: {exc}") from exc
    if not isinstance(result, AgentResult) or result.status != "ok":
        reason = result.error if isinstance(result, AgentResult) else "Runtime 返回类型错误"
        error_code = result.error_code if isinstance(result, AgentResult) else "pi_protocol"
        raise _runtime_failure(error_code, reason or "Agent Runtime 返回失败")
    if result.agent_id != profile.agent_id:
        raise ClarificationProtocolError("澄清问题的 Agent ID 与指定 Agent 不一致")
    if result.data_space != data_space.value:
        raise ClarificationProtocolError("澄清 Runtime 返回了错误的数据空间")
    question = result.structured_output.get("question")
    question_id = result.structured_output.get("question_id")
    if not isinstance(question, str) or not question.strip():
        raise ClarificationProtocolError("Runtime 澄清问题不能为空")
    if not isinstance(question_id, str) or not question_id.strip():
        raise ClarificationProtocolError("Runtime 澄清问题缺少 question_id")
    return question.strip(), question_id.strip()


def _resolve_role_key(group_chat_id: str, mention) -> str:
    if mention.target_type == "all":
        return "phd_student"
    if mention.target_type == "role":
        return mention.target_id.removeprefix("role:")
    record = get_created_group_chat(group_chat_id)
    for member in (record.members if record is not None else []):
        if member.id == mention.target_id:
            return member.role.value
    raise GroupChatMemberNotFoundError(f"成员不属于该课题组: {mention.target_id!r}")


def _response_from_record(record: dict) -> TaskClarificationResponse:
    agent_record = agents_service.get_agent_record(record["clarifier_agent_id"])
    clarifier = record["clarifier_agent_id"]
    if agent_record is not None:
        clarifier = str(agent_record.get("profile", {}).get("name") or clarifier)
    group = get_created_group_chat(record["group_chat_id"])
    group_space = getattr(getattr(group, "group_chat", None), "data_space", DataSpace.SYNTHETIC)
    return TaskClarificationResponse(
        id=record["clarification_id"],
        group_chat_id=record["group_chat_id"],
        status=record["status"],
        clarifier=clarifier,
        question_id=record.get("question_id"),
        question=record.get("question"),
        question_number=record["question_number"],
        max_questions=record.get("max_questions", MAX_QUESTIONS),
        turns=record.get("turns", []),
        error_code=record.get("error", ""),
        user_message="" if record.get("status") != "blocked" else "请检查任务准备条件后重试。",
        data_space=group_space,
        dataset_refs=[DatasetVersionRef.model_validate(item) for item in record.get("dataset_refs", [])],
    )


def _dataset_ref_json(value: DatasetVersionRef | dict) -> dict[str, object]:
    if isinstance(value, DatasetVersionRef):
        return value.model_dump(mode="json")
    return DatasetVersionRef.model_validate(value).model_dump(mode="json")


def _clarification_record(response: TaskClarificationResponse, context: dict) -> dict:
    now = time.time()
    return {
        "clarification_id": response.id,
        "group_chat_id": response.group_chat_id,
        "mention": context["mention"],
        "clarifier_agent_id": context["clarifier_agent_id"],
        "initial_intent": context["initial_intent"],
        "turns": [turn.model_dump(mode="json") for turn in response.turns],
        "status": response.status,
        "question_id": response.question_id,
        "question": response.question,
        "question_number": response.question_number,
        "max_questions": response.max_questions,
        "error": response.error_code,
        "dataset_refs": [_dataset_ref_json(item) for item in context.get("dataset_refs", [])],
        "created_at": context.get("created_at", now),
        "updated_at": now,
    }


def _save_clarification(
    response: TaskClarificationResponse, context: dict, *, create: bool = False
) -> None:
    record = _clarification_record(response, context)
    if _clarification_repository is not None:
        if create:
            _clarification_repository.create(record)
        else:
            _clarification_repository.update(response.id, record)
    if create:
        _clarifications.setdefault(response.group_chat_id, []).append(response)
    else:
        _clarifications[response.group_chat_id] = [
            response if item.id == response.id else item
            for item in _clarifications.get(response.group_chat_id, [])
        ]


def _project_clarification_response(
    response: TaskClarificationResponse,
    *,
    sender_id: str,
    reply_to_message_id: str | None,
) -> ChatMessageRecord:
    if response.status == "awaiting_answer":
        return append_chat_message(
            response.group_chat_id,
            sender_type="agent",
            sender_id=sender_id,
            content=response.question or "请补充任务所需的研究信息。",
            kind="clarification_question",
            payload={
                "clarification_id": response.id,
                "question_id": response.question_id or "",
                "question_number": response.question_number,
            },
            reply_to_message_id=reply_to_message_id,
        )
    if response.status == "ready_to_assign":
        payload = {"clarification_id": response.id}
        if response.dataset_refs:
            payload["dataset_refs"] = [item.model_dump(mode="json") for item in response.dataset_refs]
        return append_chat_message(
            response.group_chat_id,
            sender_type="agent",
            sender_id=sender_id,
            content="任务已澄清，可以开始分析。",
            kind="clarification_ready",
            payload=payload,
            reply_to_message_id=reply_to_message_id,
        )
    return append_chat_message(
        response.group_chat_id,
        sender_type="agent",
        sender_id=sender_id,
        content=response.user_message or "当前无法继续澄清，请检查任务准备条件后重试。",
        kind="clarification_blocked",
        payload={"clarification_id": response.id},
        reply_to_message_id=reply_to_message_id,
    )


def _clarification_context_for(group_chat_id: str, clarification_id: str) -> dict:
    persisted: dict | None = None
    if _clarification_repository is not None:
        record = _clarification_repository.get(clarification_id)
        if record is not None and record["group_chat_id"] == group_chat_id:
            persisted = record
    context = {
        **(_clarification_context.get(clarification_id) or {}),
        **(persisted or {}),
    }
    if context is None:
        raise ClarificationNotFoundError(f"澄清会话不存在: {clarification_id!r}")
    if not context:
        raise ClarificationNotFoundError(f"澄清会话不存在: {clarification_id!r}")

    # The clarification table stores the conversation state, while topic
    # metadata remains owned by the group record. Rehydrate it after a
    # process restart or when the in-memory context is no longer available.
    group = get_created_group_chat(group_chat_id)
    if group is not None:
        topic = getattr(group, "topic", None)
        topic_name = getattr(topic, "topic_name", "")
        topic_summary = getattr(topic, "topic_summary", "")
        if not str(context.get("topic_name") or "").strip():
            context["topic_name"] = topic_name or "未命名课题"
        if not str(context.get("topic_summary") or "").strip():
            context["topic_summary"] = topic_summary or "未提供课题概述"
    return context


def _resolve_persisted_agent(agent_id: str):
    record = agents_service.get_agent_record(agent_id)
    if record is None:
        raise ClarificationRuntimeError(f"澄清 Agent 不存在: {agent_id}")
    if not record.get("enabled", False):
        raise ClarificationRuntimeError(f"Agent 已停用，不能继续澄清: {agent_id}")
    from app.domain.schemas import AgentProfile

    try:
        return AgentProfile.model_validate(record["profile"])
    except Exception as exc:
        raise ClarificationProtocolError(f"澄清 Agent 配置无效: {agent_id}") from exc


def create_task_clarification(
    group_chat_id: str, request: TaskClarificationRequest
) -> TaskClarificationResponse:
    """创建苏格拉底式任务澄清会话（design §5.3）。

    只创建澄清记录，不启动 run、不写正式 Memory；
    澄清内容只是任务上下文，不是正式科研结论。
    """
    record = get_created_group_chat(group_chat_id)
    topic_name = (
        getattr(record.topic, "topic_name", "") if record is not None else ""
    ) or "未命名课题"
    topic_summary = record.topic.topic_summary if record is not None else ""
    question_number = 1
    clarification_id = f"clarification-{uuid.uuid4().hex}"
    group_space = getattr(getattr(record, "group_chat", None), "data_space", DataSpace.SYNTHETIC)
    canonical_dataset_refs: list[DatasetVersionRef] = []
    context = {
        "clarification_id": clarification_id,
        "group_chat_id": group_chat_id,
        "mention": request.mention.model_dump(mode="json"),
        "clarifier_agent_id": "postdoc",
        "initial_intent": request.initial_intent,
        "topic_name": topic_name,
        "topic_summary": topic_summary,
        "role_key": "",
        "source_message_id": request.source_message_id,
        "dataset_refs": [],
        "data_space": group_space.value,
        "created_at": time.time(),
    }
    try:
        profile, group_space = resolve_clarification_readiness(
            group_chat_id, request.mention
        )
        canonical_dataset_refs = _validate_dataset_refs(
            group_chat_id, request.dataset_refs, group_space
        )
        context["dataset_refs"] = [item.model_dump(mode="json") for item in canonical_dataset_refs]
        context["clarifier_agent_id"] = profile.agent_id
        context["data_space"] = group_space.value
        context["role_key"] = _resolve_role_key(group_chat_id, request.mention)
        question, question_id = _invoke_question(
            clarification_id=clarification_id,
            group_chat_id=group_chat_id,
            profile=profile,
            topic_name=topic_name,
            topic_summary=topic_summary,
            initial_intent=request.initial_intent,
            turns=[],
            question_number=question_number,
            data_space=group_space,
        )
        status = "awaiting_answer"
        response = TaskClarificationResponse(
            id=clarification_id,
            group_chat_id=group_chat_id,
            status=status,
            clarifier=profile.name,
            question_id=question_id,
            question=question,
            question_number=question_number,
            max_questions=MAX_QUESTIONS,
            turns=[],
            data_space=group_space,
            dataset_refs=canonical_dataset_refs,
        )
    except ClarificationReadinessError as exc:
        response = _blocked_response(
            clarification_id=clarification_id,
            group_chat_id=group_chat_id,
            group_space=group_space,
            error=exc,
            question_number=question_number,
            turns=[],
            dataset_refs=canonical_dataset_refs,
        )
    except ClarificationRuntimeError as exc:
        response = _blocked_response(
            clarification_id=clarification_id,
            group_chat_id=group_chat_id,
            group_space=group_space,
            error=ClarificationReadinessError(exc.code, exc.user_message),
            question_number=question_number,
            turns=[],
            dataset_refs=canonical_dataset_refs,
        )
    except ClarificationProtocolError:
        response = _blocked_response(
            clarification_id=clarification_id,
            group_chat_id=group_chat_id,
            group_space=group_space,
            error=ClarificationReadinessError(
                "clarification_protocol",
                "Agent 返回内容不符合澄清协议，请稍后重试。",
            ),
            question_number=question_number,
            turns=[],
            dataset_refs=canonical_dataset_refs,
        )
    _clarification_context[clarification_id] = context
    _save_clarification(response, context, create=True)
    _project_clarification_response(
        response,
        sender_id=str(context["clarifier_agent_id"]),
        reply_to_message_id=request.source_message_id,
    )
    return response


def _find_clarification(group_chat_id: str, clarification_id: str) -> TaskClarificationResponse:
    if _clarification_repository is not None:
        record = _clarification_repository.get(clarification_id)
        if record is not None and record["group_chat_id"] == group_chat_id:
            return _response_from_record(record)
    for response in _clarifications.get(group_chat_id, []):
        if response.id == clarification_id:
            return response
    raise ClarificationNotFoundError(f"澄清会话不存在: {clarification_id!r}")


def answer_task_clarification(
    group_chat_id: str,
    clarification_id: str,
    request: TaskClarificationAnswerRequest,
) -> TaskClarificationResponse:
    """追加一轮回答并生成下一问，最多七轮。"""
    current = _find_clarification(group_chat_id, clarification_id)
    if current.status in {"ready_to_assign", "blocked"}:
        raise ClarificationClosedError("澄清会话已完成")

    if current.question_id is None or current.question is None:
        raise ClarificationClosedError("澄清会话已完成")
    completed = [
        *current.turns,
        ClarificationTurn(
            question_id=current.question_id,
            question=current.question,
            answer=request.answer,
        ),
    ]
    context = _clarification_context_for(group_chat_id, clarification_id)
    context["source_message_id"] = request.source_message_id
    initial_intent = context["initial_intent"]
    topic_name = context.get("topic_name", "未命名课题")
    topic_summary = context.get("topic_summary", "")
    if len(completed) >= MAX_QUESTIONS or clarification_is_ready(initial_intent, completed):
        closed = current.model_copy(
            update={
                "status": "ready_to_assign",
                "question_id": None,
                "question": None,
                "turns": completed,
            }
        )
    else:
        next_number = current.question_number + 1
        try:
            profile, group_space = resolve_clarification_readiness(
                group_chat_id, MentionTarget.model_validate(context["mention"])
            )
            next_question, next_question_id = _invoke_question(
                clarification_id=clarification_id,
                group_chat_id=group_chat_id,
                profile=profile,
                topic_name=topic_name,
                topic_summary=topic_summary,
                initial_intent=initial_intent,
                turns=completed,
                question_number=next_number,
                data_space=group_space,
            )
            closed = current.model_copy(
                update={
                    "question_id": next_question_id,
                    "question": next_question,
                    "question_number": next_number,
                    "turns": completed,
                    "error": "",
                    "error_code": "",
                    "user_message": "",
                    "data_space": group_space,
                }
            )
        except ClarificationReadinessError as exc:
            closed = _blocked_response(
                clarification_id=current.id,
                group_chat_id=group_chat_id,
                group_space=current.data_space,
                error=exc,
                question_number=next_number,
                turns=completed,
                clarifier=current.clarifier,
                dataset_refs=current.dataset_refs,
            )
        except ClarificationRuntimeError as exc:
            closed = _blocked_response(
                clarification_id=current.id,
                group_chat_id=group_chat_id,
                group_space=current.data_space,
                error=ClarificationReadinessError(exc.code, exc.user_message),
                question_number=next_number,
                turns=completed,
                clarifier=current.clarifier,
                dataset_refs=current.dataset_refs,
            )
        except ClarificationProtocolError:
            closed = _blocked_response(
                clarification_id=current.id,
                group_chat_id=group_chat_id,
                group_space=current.data_space,
                error=ClarificationReadinessError(
                    "clarification_protocol",
                    "Agent 返回内容不符合澄清协议，请稍后重试。",
                ),
                question_number=next_number,
                turns=completed,
                clarifier=current.clarifier,
                dataset_refs=current.dataset_refs,
            )
    _save_clarification(closed, context)
    _project_clarification_response(
        closed,
        sender_id=str(context["clarifier_agent_id"]),
        reply_to_message_id=request.source_message_id,
    )
    return closed


def list_clarifications(
    group_chat_id: str,
) -> list[TaskClarificationResponse]:
    """按创建顺序返回该群聊的澄清记录；无记录时返回空列表。"""
    if _clarification_repository is not None:
        return [
            _response_from_record(record)
            for record in _clarification_repository.list_for_group(group_chat_id)
        ]
    return list(_clarifications.get(group_chat_id, []))


def create_formal_task(
    group_chat_id: str, clarification_id: str
) -> FormalTaskContext:
    """Freeze a completed clarification into a server-owned formal task context."""
    current = _find_clarification(group_chat_id, clarification_id)
    if current.status != "ready_to_assign":
        raise ClarificationClosedError("澄清尚未完成，不能生成正式任务")
    if _formal_task_repository is not None:
        existing = _formal_task_repository.get(clarification_id)
        if existing is not None:
            return FormalTaskContext.model_validate(existing)
    existing_fallback = _formal_tasks.get(clarification_id)
    if existing_fallback is not None:
        return FormalTaskContext.model_validate(existing_fallback)

    context = _clarification_context_for(group_chat_id, clarification_id)
    formal = FormalTaskContext(
        clarification_id=clarification_id,
        group_chat_id=group_chat_id,
        initial_intent=context["initial_intent"],
        turns=current.turns,
        topic_name=context.get("topic_name", "未命名课题"),
        topic_summary=context.get("topic_summary", ""),
        mention=MentionTarget.model_validate(context["mention"]),
        clarifier_agent_id=context["clarifier_agent_id"],
        confirmed_at=time.time(),
        data_space=current.data_space,
        dataset_refs=[DatasetVersionRef.model_validate(item) for item in context.get("dataset_refs", [])],
    )
    payload = formal.model_dump(mode="json")
    if _formal_task_repository is not None:
        _formal_task_repository.save(payload)
    _formal_tasks[clarification_id] = payload
    return formal


def reset_messages() -> None:
    """Clear messages and clarification state for demo reset/tests."""
    _messages.clear()
    if _message_repository is not None:
        _message_repository.delete_all()
    _clarifications.clear()
    _clarification_context.clear()
    _formal_tasks.clear()
    if _clarification_repository is not None:
        _clarification_repository.delete_all()
    if _formal_task_repository is not None:
        _formal_task_repository.delete_all()
