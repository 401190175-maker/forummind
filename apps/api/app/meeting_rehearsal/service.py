"""真组会预演服务的上下文快照能力。"""

from __future__ import annotations

from copy import deepcopy
import itertools
import time
from typing import Any

from app.api.runs import run_store
from app.domain.schemas import DataSpace
from app.group_chats.creation_service import get_created_group_chat
from app.meeting_rehearsal.schemas import RehearsalContext
from app.meeting_rehearsal.package_builder import build_critique, build_preparation_package
from app.meeting_rehearsal.question_bank import generate_questions
from app.meeting_rehearsal.schemas import (
    CreateMeetingRehearsalRequest,
    MeetingRehearsalSession,
    RehearsalAnswer,
    SubmitRehearsalAnswerRequest,
    RehearsalQuestionStatus,
    RehearsalSessionStatus,
)
from app.scenario.loader import load_scenario


class RehearsalError(Exception):
    """预演服务错误基类。"""


class RehearsalGroupChatNotFoundError(RehearsalError):
    """课题组不存在。"""


class RehearsalRunNotFoundError(RehearsalError):
    """绑定的 Run 不存在。"""


class RehearsalRunMismatchError(RehearsalError):
    """Run 不属于请求中的课题组。"""


class RehearsalNotFoundError(RehearsalError):
    """预演会话不存在。"""


class RehearsalQuestionNotFoundError(RehearsalError):
    """问题不属于指定预演会话。"""


class RehearsalClosedError(RehearsalError):
    """预演会话已关闭。"""


_session_seq = itertools.count(1)
_answer_seq = itertools.count(1)
_sessions: dict[str, tuple[MeetingRehearsalSession, RehearsalContext]] = {}


def _data_space(value: Any) -> str:
    return value.value if isinstance(value, DataSpace) else str(value)


def _scenario_summary(scenario: Any | None) -> str:
    final_state = getattr(scenario, "final_state", None)
    summary = getattr(final_state, "summary", "")
    return summary if isinstance(summary, str) else ""


def _step_summary(step: Any) -> dict[str, Any]:
    return {
        "id": deepcopy(getattr(step, "id", "")),
        "phase": deepcopy(getattr(step, "phase", "")),
        "kind": deepcopy(getattr(step, "kind", "")),
        "actor": deepcopy(getattr(step, "actor", "")),
        "content": deepcopy(getattr(step, "content", "")),
        "payload": deepcopy(getattr(step, "payload", {})),
        "timestamp": deepcopy(getattr(step, "timestamp", 0.0)),
    }


def _memory_summary(entry: Any) -> dict[str, Any]:
    payload = getattr(entry, "payload", {})
    return {
        "id": deepcopy(getattr(entry, "id", "")),
        "kind": deepcopy(getattr(entry, "kind", "")),
        "summary": deepcopy(
            payload.get("summary")
            or payload.get("statement")
            or payload.get("content")
            or ""
            if isinstance(payload, dict)
            else ""
        ),
    }


def build_rehearsal_context(
    group_chat: Any,
    run_state: Any | None,
    scenario: Any | None,
) -> RehearsalContext:
    """从课题组、Run 和 Scenario 构造预演所需的最小只读快照。"""
    project_group_chat = getattr(group_chat, "group_chat", group_chat)
    data_space = _data_space(getattr(project_group_chat, "data_space", ""))
    if data_space != DataSpace.SYNTHETIC.value:
        raise ValueError("真组会预演当前仅支持 synthetic 数据空间")

    topic = getattr(group_chat, "topic", group_chat)
    run_id = getattr(run_state, "run_id", None) if run_state else None
    memory = getattr(run_state, "memory", None) if run_state else None
    entries = memory.entries() if memory is not None else []
    steps = getattr(run_state, "steps", []) if run_state else []

    return RehearsalContext(
        group_chat_id=str(
            getattr(run_state, "group_chat_id", "")
            or getattr(project_group_chat, "id", "")
        ),
        topic_name=str(getattr(topic, "topic_name", "")),
        topic_summary=str(getattr(topic, "topic_summary", "")),
        run_id=run_id,
        run_phase=getattr(run_state, "phase", None) if run_state else None,
        run_cycle=getattr(run_state, "cycle", None) if run_state else None,
        step_summaries=[_step_summary(step) for step in steps],
        memory_refs=[deepcopy(entry.id) for entry in entries],
        memory_view_summaries=[_memory_summary(entry) for entry in entries],
        scenario_summary=_scenario_summary(scenario),
        data_space=DataSpace.SYNTHETIC,
    )


def _copy_session(session: MeetingRehearsalSession) -> MeetingRehearsalSession:
    return session.model_copy(deep=True)


def _get_record(
    session_id: str,
) -> tuple[MeetingRehearsalSession, RehearsalContext]:
    record = _sessions.get(session_id)
    if record is None:
        raise RehearsalNotFoundError(f"预演会话不存在: {session_id}")
    return record


def create_rehearsal(
    group_chat_id: str,
    request: CreateMeetingRehearsalRequest,
) -> MeetingRehearsalSession:
    """创建独立的进程内预演会话。"""
    group_chat = get_created_group_chat(group_chat_id)
    if group_chat is None:
        raise RehearsalGroupChatNotFoundError(f"课题组不存在: {group_chat_id}")

    run_state = None
    if request.run_id is not None:
        run_state = run_store.get(request.run_id)
        if run_state is None:
            raise RehearsalRunNotFoundError(f"Run 不存在: {request.run_id}")
        if run_state.group_chat_id != group_chat_id:
            raise RehearsalRunMismatchError("Run 与课题组不匹配")

    scenario = load_scenario("foam_concrete_case")
    context = build_rehearsal_context(group_chat, run_state, scenario)
    questions = generate_questions(
        context,
        request.intensity,
        request.personas,
        request.max_questions,
    )
    now = time.time()
    session = MeetingRehearsalSession(
        id=f"rehearsal-{next(_session_seq)}",
        group_chat_id=group_chat_id,
        run_id=request.run_id,
        intensity=request.intensity,
        personas=list(request.personas),
        questions=questions,
        created_at=now,
        updated_at=now,
    )
    _sessions[session.id] = (_copy_session(session), context.model_copy(deep=True))
    return _copy_session(session)


def get_rehearsal(session_id: str) -> MeetingRehearsalSession | None:
    """读取预演会话快照；不存在时返回 None。"""
    record = _sessions.get(session_id)
    return _copy_session(record[0]) if record else None


def submit_answer(
    session_id: str,
    request: SubmitRehearsalAnswerRequest,
) -> MeetingRehearsalSession:
    """追加一条用户应答并更新对应问题状态。"""
    session, context = _get_record(session_id)
    if session.status.value == "closed":
        raise RehearsalClosedError(f"预演会话已关闭: {session_id}")

    question = next(
        (question for question in session.questions if question.id == request.question_id),
        None,
    )
    if question is None:
        raise RehearsalQuestionNotFoundError(
            f"问题不属于预演会话: {request.question_id}"
        )

    answer = RehearsalAnswer(
        id=f"answer-{next(_answer_seq)}",
        question_id=request.question_id,
        content=request.answer,
        created_at=time.time(),
    )
    session.answers.append(answer)
    session.critiques.append(build_critique(question, session.answers, context))
    question.status = RehearsalQuestionStatus.ANSWERED
    if session.questions and all(
        item.status is RehearsalQuestionStatus.ANSWERED
        for item in session.questions
    ):
        session.status = RehearsalSessionStatus.COMPLETED
    session.updated_at = time.time()
    _sessions[session_id] = (_copy_session(session), context)
    return _copy_session(session)


def build_package(session_id: str):
    """刷新并缓存预演准备包。"""
    session, context = _get_record(session_id)
    package = build_preparation_package(session, context)
    session.preparation_package = package
    session.updated_at = time.time()
    _sessions[session_id] = (_copy_session(session), context)
    return package.model_copy(deep=True)


def reset_rehearsals() -> None:
    """清空预演 store，不影响课题组或 Run store。"""
    _sessions.clear()
