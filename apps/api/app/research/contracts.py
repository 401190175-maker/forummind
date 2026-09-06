"""Contracts for the single-agent real research loop.

These models deliberately sit between durable task data and the runtime
adapter. They contain no database or transport side effects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agent_runtime.instruction_builder import build_agent_instruction
from app.agent_runtime.schemas import AgentInstruction, AgentInvocation
from app.tasks.schemas import DatasetVersionRef


REAL_DATA_SPACES = {"real", "desensitized_real"}


def _value(source: object, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _text(source: object, name: str) -> str:
    value = _value(source, name, "")
    return str(getattr(value, "value", value)).strip()


class RealAgentInvocation(AgentInvocation):
    """Trusted invocation for a persisted real research task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    document_scope: list[str] = Field(default_factory=list)
    dataset_refs: list[DatasetVersionRef] = Field(default_factory=list)
    output_contract: Literal["research_claim"] = "research_claim"

    @field_validator("task_id")
    @classmethod
    def _trim_task_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("document_scope")
    @classmethod
    def _unique_document_scope(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("document_scope must contain non-empty strings")
        if len(set(normalized)) != len(normalized):
            raise ValueError("document_scope must contain unique document ids")
        return normalized


class CandidateClaim(BaseModel):
    """A model-produced Claim candidate, never a formal Claim by itself."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1)
    uncertainty: str = Field(min_length=1)
    next_action: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    status: Literal["candidate", "approved", "rejected"] = "candidate"
    created_at: float | None = None
    updated_at: float | None = None
    evidence: list["CandidateEvidenceRef"] = Field(default_factory=list)

    @field_validator(
        "candidate_id", "task_id", "run_id", "agent_id", "claim",
        "reasoning_summary", "uncertainty", "next_action", "data_space",
    )
    @classmethod
    def _trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must be non-empty text")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def _unique_refs(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("evidence_refs must contain non-empty strings")
        if len(set(normalized)) != len(normalized):
            raise ValueError("evidence_refs must be unique")
        return normalized


class CandidateEvidenceRef(BaseModel):
    """Resolved provenance for one candidate evidence reference."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str | None = None
    document_id: str | None = None
    group_chat_id: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    source_type: Literal["user_uploaded", "literature", "experiment"] = "user_uploaded"
    verification_status: Literal["pending", "verified", "unverified", "unavailable", "fixture"] = "pending"
    page_or_location: str = "source"
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)
    source_ref: str = Field(min_length=1)
    analysis_id: str | None = None
    dataset_id: str | None = None
    dataset_version: int | None = Field(default=None, ge=1)
    source_filename: str | None = None
    source_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _compat_source_ref(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            payload = dict(value)
            source_ref = payload.get("source_ref") or payload.get("chunk_id")
            if source_ref:
                payload["source_ref"] = source_ref
            if payload.get("source_type") == "user_uploaded" and not payload.get("chunk_id"):
                payload["chunk_id"] = source_ref
            return payload
        return value


class CandidateScope(BaseModel):
    """Server-owned scope used when validating a candidate result."""

    model_config = ConfigDict(extra="ignore")

    group_chat_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    data_space: str = Field(min_length=1)
    document_scope: list[str] = Field(default_factory=list)
    available_evidence_refs: dict[str, CandidateEvidenceRef] = Field(default_factory=dict)
    successful_source_refs: set[str] = Field(default_factory=set)

    @model_validator(mode="before")
    @classmethod
    def _accept_document_scope_alias(cls, value: Any) -> Any:
        if isinstance(value, Mapping) and "document_scope" not in value:
            value = dict(value)
            value["document_scope"] = value.get("allowed_document_ids", [])
        return value

    @field_validator("document_scope")
    @classmethod
    def _normalize_documents(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if len(set(normalized)) != len(normalized) or any(not item for item in normalized):
            raise ValueError("document_scope must contain unique non-empty strings")
        return normalized


class ValidatedCandidate(CandidateClaim):
    """Candidate plus resolved, still-pending source metadata."""

    evidence: list[CandidateEvidenceRef] = Field(default_factory=list)


def build_real_invocation(task: object, agent: object, run: object) -> RealAgentInvocation:
    """Build a trusted, task-scoped invocation without demo scenario fields."""

    task_id = _text(task, "task_id")
    group_chat_id = _text(task, "group_chat_id")
    run_group_chat_id = _text(run, "group_chat_id")
    run_id = _text(run, "run_id")
    mode = _text(run, "mode")
    data_space = _text(task, "data_space")
    if not task_id or not group_chat_id or not run_id:
        raise ValueError("real invocation requires task, group and run identity")
    if run_group_chat_id != group_chat_id:
        raise ValueError("task and run group_chat_id mismatch")
    if mode and mode != "live":
        raise ValueError("real invocation requires a live run")
    if data_space not in REAL_DATA_SPACES:
        raise ValueError("real invocation requires a real data space")
    task_status = _text(task, "status")
    if task_status not in {"ready", "running", "awaiting_review"}:
        raise ValueError(f"task is not runnable: {task_status or 'unknown'}")

    agent_id = _text(agent, "agent_id")
    role = _text(agent, "role")
    name = _text(agent, "name") or agent_id
    if not agent_id or not role:
        raise ValueError("real invocation requires agent identity and role")
    allowed_spaces = {
        _text_value(item) for item in (_value(agent, "allowed_data_spaces", []) or [])
    }
    if allowed_spaces and data_space not in allowed_spaces:
        raise ValueError("agent is not allowed to use task data space")

    document_scope = [str(item).strip() for item in (_value(task, "document_ids", []) or [])]
    if any(not item for item in document_scope) or len(set(document_scope)) != len(document_scope):
        raise ValueError("task document scope must contain unique non-empty ids")
    question = _text(task, "question")
    title = _text(task, "title")
    dataset_refs = [
        DatasetVersionRef.model_validate(item)
        for item in (_value(task, "dataset_refs", []) or [])
    ]
    task_context = dict(_value(run, "task_context", {}) or {})
    task_context.update({
        "task_id": task_id,
        "title": title,
        "question": question,
        "data_space": data_space,
        "document_ids": list(document_scope),
        "allowed_document_ids": list(document_scope),
        "dataset_refs": [item.model_dump(mode="json") for item in dataset_refs],
        "allowed_dataset_refs": [item.model_dump(mode="json") for item in dataset_refs],
    })
    profile_payload = _value(agent, "model_dump", None)
    if callable(profile_payload):
        profile_payload = profile_payload(mode="json")
    if not isinstance(profile_payload, Mapping):
        profile_payload = dict(agent) if isinstance(agent, Mapping) else {
            "agent_id": agent_id, "name": name, "role": role,
            "primary_ability": _value(agent, "primary_ability", None),
            "allowed_data_spaces": list(_value(agent, "allowed_data_spaces", []) or []),
            "allowed_tools": list(_value(agent, "allowed_tools", []) or []),
        }
    profile_tools = [str(item).strip() for item in (profile_payload.get("allowed_tools", []) or [])]
    if not profile_tools:
        profile_tools = ["knowledge.search"]
    allowed_tools = [
        name for name in profile_tools
        if name in {"knowledge.search", "experiment.analyze", "literature.search"}
        and (name != "experiment.analyze" or bool(dataset_refs))
    ]
    topic_context = {
        "name": str(task_context.get("topic_name", title or "真实研究任务")),
        "summary": str(task_context.get("topic_summary", question)),
    }
    try:
        instruction = build_agent_instruction(
            agent,
            profile_version=str(_value(run, "profile_version", "current")),
            topic_context=topic_context,
            task_context=task_context,
            phase="independent_analysis",
            allowed_tools=allowed_tools,
            output_contract="research_claim",
        )
    except (AttributeError, TypeError, ValueError):
        instruction = AgentInstruction(
            agent_id=agent_id, role=role, identity=name,
            task_context=task_context, topic_context=topic_context,
            phase="independent_analysis", allowed_tools=allowed_tools,
            output_contract="research_claim",
            safety_rules=["no_formal_memory_write", "candidate_only"],
        )
    prompt = (
        f"研究任务：{title}\n"
        f"研究问题：{question}\n"
        "请只基于授权资料生成一个候选 Claim，并返回 claim、evidence_refs、"
        "reasoning_summary、uncertainty、next_action 五个字段。"
    )
    return RealAgentInvocation(
        run_id=run_id,
        group_chat_id=group_chat_id,
        cycle=int(_value(run, "cycle", 1) or 1),
        phase="independent_analysis",
        agent_id=agent_id,
        role=role,
        profile_version=str(_value(run, "profile_version", "current")),
        agent_instruction=instruction,
        task=prompt,
        context={
            "task_id": task_id,
            "task": {"title": title, "question": question},
            "allowed_document_ids": list(document_scope),
            "document_scope": list(document_scope),
            "allowed_dataset_refs": [item.model_dump(mode="json") for item in dataset_refs],
            "agent_profile": dict(profile_payload),
        },
        allowed_tools=allowed_tools,
        output_contract="research_claim",
        data_space=data_space,
        task_id=task_id,
        document_scope=document_scope,
        dataset_refs=dataset_refs,
        safety_rules=[
            "no_formal_memory_write", "no_research_state_write",
            "no_stage_transition", "candidate_only", "no_external_data_access",
        ],
    )


def _text_value(value: object) -> str:
    return str(getattr(value, "value", value)).strip()
