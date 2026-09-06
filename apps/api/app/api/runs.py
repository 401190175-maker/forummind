"""Run API router：把编排循环状态机暴露为可轮询 HTTP 面。"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.agent_runtime.runtime_policy import resolve_runtime_policy
from app.agent_runtime.schemas import RuntimeSelection
from app.agent_runtime.instruction_builder import build_agent_instruction
from app.agents import service as agents_service
from app.agents.service import (
    AgentDisabledError,
    AgentNotFoundError,
    AgentPatchError,
    DuplicateAgentError,
)
from app.demo_data.loader import load_demo_package
from app.domain.schemas import AgentProfile
from app.documents.repository import DocumentRepository
from app.experiments.repository import ExperimentDatasetRepository
from app.group_chats.creation_service import get_created_group_chat
from app.group_chats.messages import (
    ClarificationClosedError,
    ClarificationNotFoundError,
    append_chat_message,
    create_formal_task,
    list_messages,
)
from app.memory.experiment_projection import build_experiment_view
from app.memory.projections import build_memory_views
from app.meeting.service import MeetingService
from app.orchestration.engine import (
    mark_run_failed,
    run_live_task,
    run_live_task_multi_agent,
    run_import,
    run_live,
    run_replay,
)
from app.orchestration.coordinator import MAX_AGENT_ATTEMPTS
from app.orchestration.run_store import RunState, RunStore
from app.scenario.loader import ScenarioNotFound, load_scenario
from app.storage.repositories import MeetingRepository
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask

router = APIRouter(tags=["runs"])
run_store = RunStore()
_meeting_repository: MeetingRepository | None = None
_meeting_service: MeetingService | None = None
_store: SQLiteStore | None = None
_task_repository: ResearchTaskRepository | None = None
_clarification_run_lock = threading.Lock()


def configure_persistence(store: SQLiteStore | None) -> None:
    """Configure optional durable meeting-event storage for the API."""
    global _meeting_repository, _meeting_service, _store, _task_repository
    _store = store
    _task_repository = ResearchTaskRepository(store) if store is not None else None
    _meeting_repository = MeetingRepository(store) if store is not None else None
    _meeting_service = (
        MeetingService(run_store, _meeting_repository)
        if _meeting_repository is not None
        else None
    )


class RunRequest(BaseModel):
    mode: Literal["auto", "live", "replay"] = "auto"
    clarification_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None


class DecisionRequest(BaseModel):
    option: Literal["approved", "approved_with_conditions", "returned", "deferred", "terminated"]
    reason: str


class MeetingMessageRequest(BaseModel):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _trim_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must be non-empty text")
        return value


class AgentTestRequest(BaseModel):
    task: str = Field(min_length=1)

    @field_validator("task")
    @classmethod
    def _trim_task(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("task must be non-empty text")
        return value


def _resolve_selection(mode: str) -> RuntimeSelection:
    require_pi = mode in {"auto", "live"}
    try:
        return resolve_runtime_policy(mode, require_pi=require_pi)
    except TypeError as exc:
        # Keep lightweight policy doubles with the pre-strict one-argument contract.
        if "unexpected keyword" not in str(exc):
            raise
        return resolve_runtime_policy(mode)


def _resolve_mode(mode: str) -> Literal["live", "replay"]:
    return _resolve_selection(mode).resolved_mode


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _resolve_live_agent_specs(
    group_chat: object, *, required_data_space: str | None = None
) -> list[dict]:
    """Freeze the first three enabled existing master Agents for a live Run."""
    specs: list[dict] = []
    for member in getattr(group_chat, "members", []):
        if _enum_value(getattr(member, "role", "")) != "master_student":
            continue
        if _enum_value(getattr(member, "selection_mode", "")) != "existing":
            continue
        if _enum_value(getattr(member, "status", "")) != "active":
            continue
        reference = getattr(member, "agent_profile_ref", None)
        object_id = getattr(reference, "object_id", "")
        agent_id = str(object_id).rsplit(":", 1)[-1]
        record = agents_service.get_agent_record(agent_id)
        if record is None:
            raise ValueError(f"live Run 的 Agent 不存在: {agent_id}")
        if not record["enabled"]:
            raise ValueError(f"live Run 的 Agent 已停用: {agent_id}")
        profile = AgentProfile.model_validate(record["profile"])
        allowed_spaces = {_enum_value(space) for space in profile.allowed_data_spaces}
        if (
            required_data_space
            and allowed_spaces
            and required_data_space not in allowed_spaces
        ):
            continue
        if any(spec["agent_id"] == profile.agent_id for spec in specs):
            raise ValueError(f"live Run 的 Agent ID 重复: {profile.agent_id}")
        specs.append(
            {
                "agent_id": profile.agent_id,
                "name": profile.name,
                "role": _enum_value(profile.role),
                "primary_ability": profile.primary_ability,
                "secondary_abilities": list(profile.secondary_abilities),
                "general_research_abilities": list(profile.general_research_abilities),
                "allowed_data_spaces": [
                    _enum_value(space) for space in profile.allowed_data_spaces
                ],
                "allowed_tools": list(profile.allowed_tools),
                "specialty_domain": profile.specialty_domain,
                "knowledge_base_coverage": profile.knowledge_base_coverage,
                "forbidden_actions": profile.forbidden_actions,
                "profile_version": "current",
                "profile": profile.model_dump(mode="json"),
            }
        )
        if len(specs) == 3:
            break
    if len(specs) < 3:
        raise ValueError("live Run 至少需要三个启用的 existing master_student Agent")
    return specs


def _resolve_review_agent_spec(group_chat: object) -> dict:
    """Freeze the configured PhD Agent for the pre-meeting review gate."""
    for member in getattr(group_chat, "members", []):
        if _enum_value(getattr(member, "role", "")) != "phd_student":
            continue
        if _enum_value(getattr(member, "selection_mode", "")) != "existing":
            continue
        if _enum_value(getattr(member, "status", "")) != "active":
            continue
        reference = getattr(member, "agent_profile_ref", None)
        agent_id = str(getattr(reference, "object_id", "")).rsplit(":", 1)[-1]
        record = agents_service.get_agent_record(agent_id)
        if record is None or not record["enabled"]:
            continue
        profile = AgentProfile.model_validate(record["profile"])
        if _enum_value(profile.role) != "phd_student":
            continue
        return {
            "agent_id": profile.agent_id,
            "name": profile.name,
            "role": _enum_value(profile.role),
            "primary_ability": profile.primary_ability,
            "secondary_abilities": list(profile.secondary_abilities),
            "general_research_abilities": list(profile.general_research_abilities),
            "allowed_data_spaces": [_enum_value(space) for space in profile.allowed_data_spaces],
            "allowed_tools": list(profile.allowed_tools),
            "specialty_domain": profile.specialty_domain,
            "knowledge_base_coverage": profile.knowledge_base_coverage,
            "forbidden_actions": profile.forbidden_actions,
            "profile_version": "current",
            "profile": profile.model_dump(mode="json"),
        }
    return {}


def _resolve_postdoc_agent_spec(group_chat: object) -> dict:
    """Freeze the configured Postdoc Agent for task-scoped synthesis."""
    for member in getattr(group_chat, "members", []):
        if _enum_value(getattr(member, "role", "")) != "postdoc":
            continue
        if _enum_value(getattr(member, "selection_mode", "")) != "existing":
            continue
        if _enum_value(getattr(member, "status", "")) != "active":
            continue
        reference = getattr(member, "agent_profile_ref", None)
        agent_id = str(getattr(reference, "object_id", "")).rsplit(":", 1)[-1]
        record = agents_service.get_agent_record(agent_id)
        if record is None or not record["enabled"]:
            continue
        profile = AgentProfile.model_validate(record["profile"])
        if _enum_value(profile.role) != "postdoc":
            continue
        return {
            "agent_id": profile.agent_id,
            "name": profile.name,
            "role": _enum_value(profile.role),
            "primary_ability": profile.primary_ability,
            "secondary_abilities": list(profile.secondary_abilities),
            "general_research_abilities": list(profile.general_research_abilities),
            "allowed_data_spaces": [_enum_value(space) for space in profile.allowed_data_spaces],
            "allowed_tools": list(profile.allowed_tools),
            "specialty_domain": profile.specialty_domain,
            "knowledge_base_coverage": profile.knowledge_base_coverage,
            "forbidden_actions": profile.forbidden_actions,
            "profile_version": "current",
            "profile": profile.model_dump(mode="json"),
        }
    return {}


def _freeze_agent_instructions(
    group_chat: object, specs: list[dict], task_context: dict
) -> list[dict]:
    """Freeze the profile and its rendered instruction into a Run snapshot."""
    topic = getattr(group_chat, "topic", None)
    topic_context = {
        "name": getattr(topic, "topic_name", "泡沫混凝土课题"),
        "summary": getattr(topic, "topic_summary", "合成科研课题"),
    }
    frozen: list[dict] = []
    for spec in specs:
        item = dict(spec)
        profile = AgentProfile.model_validate(item.get("profile", item))
        instruction = build_agent_instruction(
            profile,
            profile_version=str(item.get("profile_version", "current")),
            topic_context=topic_context,
            task_context=dict(task_context),
            phase="independent_analysis",
            output_contract="claim_four_fields",
        )
        item["agent_instruction"] = instruction.model_dump(mode="json")
        frozen.append(item)
    return frozen


def _freeze_review_instruction(
    group_chat: object, spec: dict, task_context: dict
) -> dict:
    topic = getattr(group_chat, "topic", None)
    topic_context = {
        "name": getattr(topic, "topic_name", "泡沫混凝土课题"),
        "summary": getattr(topic, "topic_summary", "合成科研课题"),
    }
    item = dict(spec)
    profile = AgentProfile.model_validate(item.get("profile", item))
    instruction = build_agent_instruction(
        profile,
        profile_version=str(item.get("profile_version", "current")),
        topic_context=topic_context,
        task_context=dict(task_context),
        phase="review_gate",
        allowed_tools=list(item.get("allowed_tools", profile.allowed_tools)),
        output_contract="review_gate",
    )
    item["agent_instruction"] = instruction.model_dump(mode="json")
    return item


def _freeze_postdoc_instruction(
    group_chat: object, spec: dict, task_context: dict
) -> dict:
    topic = getattr(group_chat, "topic", None)
    topic_context = {
        "name": getattr(topic, "topic_name", "泡沫混凝土课题"),
        "summary": getattr(topic, "topic_summary", "合成科研课题"),
    }
    item = dict(spec)
    profile = AgentProfile.model_validate(item.get("profile", item))
    instruction = build_agent_instruction(
        profile,
        profile_version=str(item.get("profile_version", "current")),
        topic_context=topic_context,
        task_context=dict(task_context),
        phase="postdoc_exchange",
        allowed_tools=list(item.get("allowed_tools", profile.allowed_tools)),
        output_contract="postdoc_synthesis",
    )
    item["agent_instruction"] = instruction.model_dump(mode="json")
    return item


def _profile_from_frozen_spec(spec: dict) -> AgentProfile:
    return AgentProfile.model_validate(spec.get("profile", spec))


def is_multi_agent_task_run(state: RunState) -> bool:
    """Identify the additive P2 task path without changing P1 Runs."""
    masters = [
        spec for spec in state.agent_specs
        if _enum_value(spec.get("role", "")) == "master_student"
    ]
    return (
        state.mode == "live"
        and state.task_context.get("completion_mode") == "candidate_review"
        and len(masters) >= 3
    )


def _scenario():
    try:
        return load_scenario("foam_concrete_case")
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=500, detail="剧本配置错误") from exc


def _group_agent(group_chat: object, agent_id: str) -> AgentProfile:
    for member in getattr(group_chat, "members", []):
        reference = getattr(member, "agent_profile_ref", None)
        member_agent_id = str(getattr(reference, "object_id", "")).rsplit(":", 1)[-1]
        if member_agent_id != agent_id:
            continue
        if _enum_value(getattr(member, "status", "")) != "active":
            raise HTTPException(status_code=409, detail="Agent 未处于可运行状态")
        record = agents_service.get_agent_record(agent_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Agent 不存在")
        if not record["enabled"]:
            raise HTTPException(status_code=409, detail="Agent 已停用")
        return AgentProfile.model_validate(record["profile"])
    raise HTTPException(status_code=404, detail="Agent 不属于当前课题组")


def _start_task_live_run(group_chat_id: str, body: RunRequest) -> dict:
    if _store is None or _task_repository is None:
        raise HTTPException(status_code=503, detail="真实研究任务存储未配置")
    if not body.task_id:
        raise HTTPException(status_code=422, detail="live 任务运行需要 task_id")
    if not body.agent_id:
        raise HTTPException(status_code=422, detail="live 任务运行需要 agent_id")
    group_chat = get_created_group_chat(group_chat_id)
    if group_chat is None:
        raise HTTPException(status_code=404, detail="课题组不存在，不能启动 run")
    task = _task_repository.get_for_group(body.task_id, group_chat_id)
    if task is None:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    if task.status != "ready":
        raise HTTPException(status_code=409, detail=f"研究任务当前不可运行：{task.status}")
    documents = DocumentRepository(_store)
    for document_id in task.document_ids:
        document = documents.get_for_group(document_id, group_chat_id)
        job = documents.get_index_job(document_id)
        if document is None or document.status != "ready" or job is None or job.status != "ready":
            raise HTTPException(status_code=409, detail=f"文档尚未完成索引：{document_id}")
    agent = _group_agent(group_chat, body.agent_id)
    dataset_refs = [item.model_dump(mode="json") for item in task.dataset_refs]
    task_context = {
        "task_id": task.task_id,
        "title": task.title,
        "question": task.question,
        "data_space": task.data_space,
        "document_ids": list(task.document_ids),
        "allowed_document_ids": list(task.document_ids),
        "dataset_refs": dataset_refs,
        "allowed_dataset_refs": list(dataset_refs),
        "allowed_source_data_spaces": [task.data_space, "verifiable_public"],
    }
    multi_agent_specs: list[dict] = []
    review_spec: dict = {}
    postdoc_spec: dict = {}
    multi_task_context = {
        **task_context,
        "task": task.question,
        "output_contract": "research_claim",
        "completion_mode": "candidate_review",
    }
    try:
        multi_agent_specs = _resolve_live_agent_specs(
            group_chat, required_data_space=_enum_value(task.data_space)
        )
        if len(multi_agent_specs) >= 3:
            multi_agent_specs = _freeze_agent_instructions(
                group_chat, multi_agent_specs, multi_task_context
            )
            review_spec = _resolve_review_agent_spec(group_chat)
            if review_spec:
                review_spec = _freeze_review_instruction(
                    group_chat, review_spec, multi_task_context
                )
            postdoc_spec = _resolve_postdoc_agent_spec(group_chat)
            if postdoc_spec:
                postdoc_spec = _freeze_postdoc_instruction(
                    group_chat, postdoc_spec, multi_task_context
                )
    except (TypeError, ValueError):
        # A group that is not P2-ready continues through the P1 single-Agent path.
        multi_agent_specs = []

    p2_enabled = len(multi_agent_specs) >= 3
    state = run_store.create(
        group_chat_id,
        "live",
        task_id=task.task_id,
        agent_specs=(
            multi_agent_specs
            if p2_enabled
            else [agent.model_dump(mode="json")]
        ),
        review_agent_spec=review_spec if p2_enabled else None,
        postdoc_agent_spec=postdoc_spec if p2_enabled else None,
        runtime_name="pi",
        task_context=multi_task_context if p2_enabled else task_context,
    )
    run_store.ensure_run_started_event(state, agent_id=agent.agent_id)
    _task_repository.set_status(task.task_id, "running")

    def execute() -> None:
        try:
            if p2_enabled:
                result = asyncio.run(
                    run_live_task_multi_agent(
                        task,
                        [_profile_from_frozen_spec(spec) for spec in multi_agent_specs],
                        store=_store,
                        run_store=run_store,
                        state=state,
                        review_agent=(
                            _profile_from_frozen_spec(review_spec)
                            if review_spec else None
                        ),
                        postdoc_agent=(
                            _profile_from_frozen_spec(postdoc_spec)
                            if postdoc_spec else None
                        ),
                        meeting_service=_meeting_service,
                    )
                )
            else:
                result = asyncio.run(
                    run_live_task(
                        task,
                        agent,
                        store=_store,
                        run_store=run_store,
                        state=state,
                    )
                )
            next_status = "awaiting_review" if result.status == "awaiting_review" else result.status
            if next_status in {"awaiting_review", "completed", "failed", "cancelled"}:
                _task_repository.set_status(task.task_id, next_status)
                _project_terminal_run_message(result)
        except Exception as exc:
            mark_run_failed(state, error=f"real task runtime failed: {exc}", runtime_name="pi")
            _task_repository.set_status(task.task_id, "failed")
            _project_terminal_run_message(state)

    threading.Thread(target=execute, daemon=True).start()
    return {"run_id": state.run_id, "status": state.status}


def retry_live_task_agent(run_id: str, agent_id: str = "") -> RunState:
    """Resume one failed P2 Agent while preserving the frozen Run snapshot."""
    state = run_store.get(run_id)
    if state is None:
        raise ValueError("Run 不存在")
    if not is_multi_agent_task_run(state):
        return state
    if state.status != "failed":
        raise ValueError("只能重试 failed Run")
    if _store is None or _task_repository is None:
        raise ValueError("真实研究任务存储未配置")

    target_id = (agent_id or state.current_agent_id).strip()
    frozen_specs = [*state.agent_specs]
    if state.review_agent_spec:
        frozen_specs.append(state.review_agent_spec)
    if state.postdoc_agent_spec:
        frozen_specs.append(state.postdoc_agent_spec)
    if not any(str(spec.get("agent_id", "")) == target_id for spec in frozen_specs):
        raise ValueError("retry agent 不属于当前 Run")
    latest_invocation = next(
        (
            step
            for step in reversed(state.steps)
            if step.kind == "invocation" and step.actor == target_id
        ),
        None,
    )
    if latest_invocation is None:
        raise ValueError(f"没有找到 Agent 的失败 invocation: {target_id}")
    if latest_invocation.payload.get("status") == "ok":
        raise ValueError(f"只能重试最近一次失败 invocation: {target_id}")
    attempts = int(state.agent_attempts.get(target_id, 0))
    if attempts >= MAX_AGENT_ATTEMPTS:
        raise ValueError(f"Agent 已达到最大重试次数: {target_id}")

    task = _task_repository.get_for_group(state.task_id, state.group_chat_id)
    if task is None:
        raise ValueError("研究任务不存在")
    state.control_state = "retry_requested"
    state.status = "running"
    state.error = ""
    state.persist()
    _task_repository.set_status(task.task_id, "running")
    meeting_service = _meeting_service

    def execute() -> None:
        try:
            result = asyncio.run(
                run_live_task_multi_agent(
                    task,
                    [_profile_from_frozen_spec(spec) for spec in state.agent_specs],
                    store=_store,
                    run_store=run_store,
                    state=state,
                    review_agent=(
                        _profile_from_frozen_spec(state.review_agent_spec)
                        if state.review_agent_spec else None
                    ),
                    postdoc_agent=(
                        _profile_from_frozen_spec(state.postdoc_agent_spec)
                        if state.postdoc_agent_spec else None
                    ),
                    meeting_service=meeting_service,
                    retry_agent_id=target_id,
                )
            )
            next_status = "awaiting_review" if result.status == "awaiting_review" else result.status
            if next_status in {"awaiting_review", "completed", "failed", "cancelled"}:
                _task_repository.set_status(task.task_id, next_status)
                _project_terminal_run_message(result)
        except Exception as exc:
            mark_run_failed(
                state,
                error=f"real task retry failed: {exc}",
                runtime_name="pi",
                meeting_service=meeting_service,
            )
            _task_repository.set_status(task.task_id, "failed")
            _project_terminal_run_message(state)

    threading.Thread(target=execute, daemon=True).start()
    return state


def _clarification_reply_message_id(
    group_chat_id: str, clarification_id: str
) -> str | None:
    for message in reversed(list_messages(group_chat_id)):
        if message.payload.get("clarification_id") == clarification_id:
            return message.reply_to_message_id
    return None


def _start_live_run_from_clarification(
    group_chat_id: str, clarification_id: str
) -> dict:
    with _clarification_run_lock:
        return _start_live_run_from_clarification_locked(group_chat_id, clarification_id)


def _start_live_run_from_clarification_locked(
    group_chat_id: str, clarification_id: str
) -> dict:
    try:
        formal_task = create_formal_task(group_chat_id, clarification_id)
    except (ClarificationNotFoundError, ClarificationClosedError) as exc:
        raise HTTPException(
            status_code=409,
            detail="请先完成任务澄清，再开始分析。",
        ) from exc
    if _store is None or _task_repository is None:
        raise HTTPException(status_code=503, detail="真实研究任务存储未配置")

    group_chat = get_created_group_chat(group_chat_id)
    if group_chat is None:
        raise HTTPException(status_code=404, detail="课题组不存在，不能启动分析")
    group_space = _enum_value(getattr(group_chat.group_chat, "data_space", ""))
    if group_space not in {"real", "desensitized_real"}:
        raise HTTPException(
            status_code=409,
            detail="当前课题组尚未配置为可分析的研究资料空间。",
        )
    selection = _resolve_selection("live")
    if selection.runtime_name == "unavailable":
        raise HTTPException(
            status_code=409,
            detail="研究服务暂时不可用，尚未开始分析。",
        )
    documents = DocumentRepository(_store)
    document_ids = [
        document.document_id
        for document in documents.list_for_group(group_chat_id)
        if document.status == "ready"
        and document.data_space == group_space
        and (job := documents.get_index_job(document.document_id)) is not None
        and job.status == "ready"
    ]
    dataset_refs = list(formal_task.dataset_refs)
    if dataset_refs:
        datasets = ExperimentDatasetRepository(_store)
        for dataset_ref in dataset_refs:
            dataset = datasets.get(dataset_ref.dataset_id, dataset_ref.version)
            if dataset is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"指定的实验数据集版本不可用: {dataset_ref.dataset_id}:v{dataset_ref.version}",
                )
            if dataset.group_chat_id != group_chat_id:
                raise HTTPException(status_code=409, detail="实验数据集不属于当前课题组")
            if dataset.data_space != group_space:
                raise HTTPException(status_code=409, detail="实验数据集数据空间与课题组不一致")
    elif not document_ids:
        raise HTTPException(
            status_code=409,
            detail="请先上传资料，并等待资料处理完成后再开始分析。",
        )
    try:
        agent = _group_agent(group_chat, formal_task.clarifier_agent_id)
    except HTTPException as exc:
        raise HTTPException(
            status_code=409,
            detail="该成员暂未完成运行配置，不能接收此任务。",
        ) from exc
    if group_space not in {_enum_value(space) for space in agent.allowed_data_spaces}:
        raise HTTPException(
            status_code=409,
            detail="该成员无权访问当前课题组资料，请更换已授权成员。",
        )
    if "knowledge.search" not in agent.allowed_tools:
        raise HTTPException(
            status_code=409,
            detail="该成员暂未完成运行配置，不能接收此任务。",
        )

    task = _task_repository.get_for_clarification(group_chat_id, clarification_id)
    if task is not None:
        existing_run = run_store.get_latest_for_task(group_chat_id, task.task_id)
        if existing_run is not None and existing_run.status not in {"failed", "cancelled"}:
            return {"run_id": existing_run.run_id, "status": existing_run.status}
    if task is None:
        now = time.time()
        created = ResearchTask(
            task_id=f"task-{uuid4().hex}",
            group_chat_id=group_chat_id,
            title=formal_task.initial_intent[:200],
            question=formal_task.initial_intent,
            source_clarification_id=clarification_id,
            document_ids=document_ids,
            dataset_refs=dataset_refs,
            data_space=group_space,
            status="ready",
            created_at=now,
            updated_at=now,
        )
        try:
            task = _task_repository.create(created)
        except sqlite3.IntegrityError:
            task = _task_repository.get_for_clarification(
                group_chat_id, clarification_id
            )
            if task is None:
                raise
    response = _start_task_live_run(
        group_chat_id,
        RunRequest(mode="live", task_id=task.task_id, agent_id=agent.agent_id),
    )
    append_chat_message(
        group_chat_id,
        sender_type="agent",
        sender_id="postdoc",
        content="已开始分析课题组资料。",
        kind="run_status",
        payload={"run_id": response["run_id"], "status": response["status"]},
        reply_to_message_id=_clarification_reply_message_id(
            group_chat_id, clarification_id
        ),
    )
    return response


def _project_terminal_run_message(state: RunState) -> None:
    status = str(state.status)
    if status == "awaiting_review":
        kind = "candidate"
        content = "已生成候选结果，等待你审阅。"
    elif status == "completed":
        kind = "run_status"
        content = "分析已完成。"
    elif status in {"failed", "cancelled"}:
        kind = "run_status"
        content = "分析未能完成，请检查资料和成员配置后重试。"
    else:
        return

    if any(
        message.kind == kind
        and message.payload.get("run_id") == state.run_id
        and message.payload.get("status") == status
        for message in list_messages(state.group_chat_id)
    ):
        return

    reply_to_message_id = None
    task = _task_repository.get_for_group(state.task_id, state.group_chat_id) if _task_repository else None
    if task is not None and task.source_clarification_id:
        reply_to_message_id = _clarification_reply_message_id(
            state.group_chat_id, task.source_clarification_id
        )
    payload = {"run_id": state.run_id, "status": status}
    if kind == "candidate" and state.task_context.get("candidate_id"):
        payload["candidate_id"] = state.task_context["candidate_id"]
    append_chat_message(
        state.group_chat_id,
        sender_type="agent",
        sender_id="postdoc",
        content=content,
        kind=kind,
        payload=payload,
        reply_to_message_id=reply_to_message_id,
    )


def _snapshot(state: RunState) -> dict:
    entries = state.memory.entries()
    tool_calls = [
        {
            "record_id": record.record_id,
            "request_id": record.request_id,
            "tool_name": record.tool_name,
            "tool_version": record.tool_version,
            "authorization": record.authorization,
            "status": record.status,
            "run_id": record.run_id,
            "group_chat_id": record.group_chat_id,
            "cycle": record.cycle,
            "phase": record.phase,
            "agent_id": record.agent_id,
            "role": record.role,
            "runtime": record.runtime,
            "source_refs": list(record.source_refs),
            "result_summary": dict(record.result_summary),
            "requested_data_space": record.requested_data_space,
            "returned_data_space": record.returned_data_space,
            "policy_version": record.policy_version,
            "error_code": record.error_code,
            "duration_ms": record.duration_ms,
        }
        for record in getattr(state, "tool_audit_records", [])
    ]
    return {
        "run_id": state.run_id,
        "status": state.status,
        "mode": state.mode,
        "phase": state.phase,
        "cycle": state.cycle,
        "agent_specs": [dict(spec) for spec in state.agent_specs],
        "review_agent_spec": dict(state.review_agent_spec),
        "runtime_name": state.runtime_name,
        "task_context": dict(state.task_context),
        "artifacts": [dict(artifact) for artifact in state.artifacts],
        "error": state.error,
        "steps": [
            {"id": s.id, "phase": s.phase, "kind": s.kind, "actor": s.actor,
             "content": s.content, "payload": s.payload, "timestamp": s.timestamp}
            for s in state.steps
        ],
        "memory": [
            {"id": e.id, "kind": e.kind, "payload": e.payload, "version": e.version,
             "supersedes": e.supersedes, "created_at": e.created_at,
             "object_key": e.object_key, "data_space": e.data_space}
            for e in entries
        ],
        # Memory 三视图投影（design §5.6）：raw memory 保留，视图为只读派生。
        "memory_views": build_memory_views(entries),
        "experiment_view": build_experiment_view(
            phase=state.phase,
            steps=state.steps,
            entries=entries,
        ),
        "tool_calls": tool_calls,
    }


def _get_state(run_id: str) -> RunState:
    state = run_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return state


@router.post("/group-chats/{group_chat_id}/runs")
def start_run(group_chat_id: str, body: RunRequest) -> dict:
    if get_created_group_chat(group_chat_id) is None:
        raise HTTPException(status_code=404, detail="课题组不存在，不能启动 run")
    if body.mode == "live" and body.clarification_id and not body.task_id:
        return _start_live_run_from_clarification(
            group_chat_id, body.clarification_id
        )
    if body.mode == "live" and body.task_id:
        return _start_task_live_run(group_chat_id, body)
    scenario = _scenario()
    selection = _resolve_selection(body.mode)
    resolved = selection.resolved_mode
    task_context: dict = {}
    if body.clarification_id:
        try:
            formal_task = create_formal_task(group_chat_id, body.clarification_id)
        except ClarificationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ClarificationClosedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        task_context = formal_task.model_dump(mode="json")
    if resolved == "replay":
        state = run_store.create(group_chat_id, resolved, task_context=task_context)
        run_replay(scenario, state)
    else:
        review_spec: dict = {}
        try:
            specs = _resolve_live_agent_specs(get_created_group_chat(group_chat_id))
            specs = _freeze_agent_instructions(
                get_created_group_chat(group_chat_id), specs, task_context
            )
            review_spec = _resolve_review_agent_spec(get_created_group_chat(group_chat_id))
            if review_spec:
                review_spec = _freeze_review_instruction(
                    get_created_group_chat(group_chat_id), review_spec, task_context
                )
        except ValueError as exc:
            state = run_store.create(
                group_chat_id,
                "live",
                runtime_name=selection.runtime_name or "unavailable",
                task_context=task_context,
                review_agent_spec=review_spec,
            )
            mark_run_failed(
                state,
                error=str(exc),
                runtime_name=selection.runtime_name or "unavailable",
                meeting_service=_meeting_service,
            )
            return {"run_id": state.run_id, "status": state.status}
        state = run_store.create(
            group_chat_id,
            "live",
            agent_specs=specs,
            runtime_name=selection.runtime_name or "unavailable",
            task_context=task_context,
            review_agent_spec=review_spec,
        )
        if selection.runtime_name == "unavailable":
            mark_run_failed(
                state,
                error=selection.fallback_reason or "Pi runtime 不可用",
                runtime_name="unavailable",
                meeting_service=_meeting_service,
            )
            return {"run_id": state.run_id, "status": state.status}
        meeting_service = _meeting_service
        threading.Thread(
            target=lambda: asyncio.run(
                run_live(scenario, state, meeting_service=meeting_service)
            ),
            daemon=True,
        ).start()
    return {"run_id": state.run_id, "status": state.status}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _snapshot(_get_state(run_id))


@router.get("/runs/{run_id}/meeting-events")
def get_meeting_events(run_id: str) -> list[dict]:
    _get_state(run_id)
    if _meeting_service is None:
        raise HTTPException(status_code=503, detail="会议事件持久化未配置")
    return [event.model_dump(mode="json") for event in _meeting_service.list_meeting_events(run_id)]


@router.post("/runs/{run_id}/meeting-messages")
def append_meeting_message(run_id: str, body: MeetingMessageRequest) -> dict:
    _get_state(run_id)
    if _meeting_service is None:
        raise HTTPException(status_code=503, detail="会议事件持久化未配置")
    try:
        event = _meeting_service.append_pi_message(run_id, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return event.model_dump(mode="json")


@router.post("/runs/{run_id}/decision")
def decide(run_id: str, body: DecisionRequest) -> dict:
    state = _get_state(run_id)
    if _meeting_service is None:
        raise HTTPException(status_code=503, detail="会议事件持久化未配置")
    try:
        _meeting_service.apply_pi_decision(run_id, body.option, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _snapshot(state)


@router.post("/runs/{run_id}/experiment-results")
def import_results(run_id: str) -> dict:
    state = _get_state(run_id)
    try:
        run_import(_scenario(), state)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _snapshot(state)


def _agent_projection(record: dict) -> dict:
    profile = AgentProfile.model_validate(record["profile"])
    payload = profile.model_dump(mode="json")
    payload["enabled"] = record["enabled"]
    latest = agents_service.get_latest_test_result(profile.agent_id)
    payload["latest_test"] = (
        None if latest is None else latest.model_dump(mode="json")
    )
    return payload


def _agent_response(agent_id: str) -> dict:
    record = agents_service.get_agent_record(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return _agent_projection(record)


@router.get("/agents")
def list_agents() -> dict:
    return {
        "data_space": "synthetic",
        "agents": [
            _agent_projection(record)
            for record in agents_service.list_agent_records()
        ],
    }


@router.post("/agents")
def create_agent(profile: AgentProfile) -> dict:
    try:
        created = agents_service.create_agent(profile)
    except DuplicateAgentError as exc:
        raise HTTPException(status_code=409, detail="Agent ID 已存在") from exc
    except AgentPatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _agent_response(created.agent_id)


@router.patch("/agents/{agent_id}")
def update_agent(agent_id: str, patch: dict[str, object]) -> dict:
    try:
        updated = agents_service.update_agent(agent_id, patch)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent 不存在") from exc
    except AgentPatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _agent_response(updated.agent_id)


@router.post("/agents/{agent_id}/test")
async def test_agent(agent_id: str, body: AgentTestRequest) -> dict:
    try:
        result = await agents_service.test_agent(agent_id, body.task)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent 不存在") from exc
    except AgentDisabledError as exc:
        raise HTTPException(status_code=409, detail="Agent 已停用，不能执行测试") from exc
    except AgentPatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except agents_service.AgentTaskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.model_dump(mode="json")
