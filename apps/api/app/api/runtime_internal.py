"""Private HTTP boundary used by the native Node runtime for governed tools."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.agent_runtime.schemas import AgentInvocation
from app.api.runs import run_store
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.search import KnowledgeSearch
from app.experiments.repository import ExperimentDatasetRepository
from app.storage.sqlite_store import SQLiteStore
from app.tools import build_real_registry, build_synthetic_registry
from app.tools.context import build_tool_execution_context
from app.tools.schemas import ToolRequest
from app.tasks.schemas import DatasetVersionRef
from app.orchestration.engine import _live_literature_search
from app.literature.repository import LiteratureLeadRepository

router = APIRouter(tags=["internal"], include_in_schema=False)
_knowledge_search: KnowledgeSearch | None = None


def configure_persistence(store: SQLiteStore | None) -> None:
    global _knowledge_search
    _knowledge_search = KnowledgeSearch(KnowledgeRepository(store)) if store is not None else None


class RuntimeToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    run_id: str
    group_chat_id: str
    agent_id: str
    role: str = ""
    phase: str = ""
    cycle: int | None = None
    input_refs: list[str] = Field(default_factory=list)
    data_space: str = "synthetic"
    task_id: str = ""
    document_scope: list[str] = Field(default_factory=list)
    session_id: str = ""
    invocation_id: str = ""
    attempt: int | None = Field(default=None, ge=1)


def _runtime_token() -> str:
    return os.getenv("PI_RUNTIME_TOKEN", "").strip()


def _check_token(value: str | None) -> None:
    expected = _runtime_token()
    if not expected or value != expected:
        raise HTTPException(status_code=401, detail="runtime token required")


@router.post("/internal/runtime/tool-calls")
def execute_runtime_tool(
    body: RuntimeToolCallRequest,
    x_forummind_runtime_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_forummind_runtime_token)
    state = run_store.get(body.run_id)
    if state is None or state.group_chat_id != body.group_chat_id:
        raise HTTPException(status_code=404, detail="run not found")
    spec = next((item for item in state.agent_specs if item.get("agent_id") == body.agent_id), None)
    if spec is None and state.review_agent_spec.get("agent_id") == body.agent_id:
        spec = state.review_agent_spec
    if spec is None and state.postdoc_agent_spec.get("agent_id") == body.agent_id:
        spec = state.postdoc_agent_spec
    if spec is None:
        raise HTTPException(status_code=403, detail="agent is not part of run")
    if state.current_agent_id and body.agent_id != state.current_agent_id:
        raise HTTPException(status_code=403, detail="current agent mismatch")
    if body.invocation_id and state.current_invocation_id:
        if body.invocation_id != state.current_invocation_id:
            raise HTTPException(status_code=403, detail="invocation identity mismatch")
    if body.attempt is not None:
        expected_attempt = getattr(state, "agent_attempts", {}).get(body.agent_id)
        if expected_attempt is not None and body.attempt != expected_attempt:
            raise HTTPException(status_code=403, detail="attempt identity mismatch")
    if body.session_id:
        session_refs = getattr(state, "session_refs", {})
        matching = [
            ref for ref in session_refs.values()
            if ref.agent_id == body.agent_id
            and (not body.invocation_id or ref.invocation_id == body.invocation_id)
            and (body.attempt is None or ref.attempt == body.attempt)
        ]
        if not any(ref.session_id == body.session_id for ref in matching):
            raise HTTPException(status_code=403, detail="session identity mismatch")
    instruction = spec.get("agent_instruction") or None
    data_space = str(state.task_context.get("data_space", "synthetic"))
    task_id = str(state.task_context.get("task_id", ""))
    allowed_document_ids = list(state.task_context.get(
        "allowed_document_ids", state.task_context.get("document_ids", [])
    ))
    allowed_dataset_refs = [
        DatasetVersionRef.model_validate(item)
        for item in state.task_context.get("allowed_dataset_refs", state.task_context.get("dataset_refs", []))
    ]
    if body.task_id and body.task_id != task_id:
        raise HTTPException(status_code=403, detail="task_id_mismatch")
    if body.document_scope and body.document_scope != allowed_document_ids:
        raise HTTPException(status_code=403, detail="document_scope_mismatch")
    invocation = AgentInvocation(
        run_id=state.run_id,
        group_chat_id=state.group_chat_id,
        cycle=body.cycle or state.cycle,
        phase=state.current_phase or state.phase,
        agent_id=body.agent_id,
        role=str(spec.get("role", "")),
        profile_version=str(spec.get("profile_version", "current")),
        agent_instruction=instruction,
        task="native tool call",
        input_refs=list(spec.get("input_refs", body.input_refs)),
        context={},
        allowed_tools=list(spec.get("allowed_tools", [])),
        output_contract=str(spec.get("output_contract", "free_text")),
        data_space=data_space,
        task_id=task_id,
        document_scope=allowed_document_ids,
        dataset_refs=allowed_dataset_refs,
        safety_rules=[],
    )
    if body.data_space != invocation.data_space:
        raise HTTPException(status_code=403, detail="data_space_mismatch")
    context = build_tool_execution_context(
        invocation,
        runtime_name="pi",
        memory_entries=list(state.memory.entries()),
        experiment_view={"steps": [step.payload for step in state.steps]},
        task_id=task_id,
        allowed_document_ids=allowed_document_ids,
        allowed_dataset_refs=allowed_dataset_refs,
    )
    request = ToolRequest(
        request_id=body.request_id,
        name=body.name,
        arguments=body.arguments,
        data_space=body.data_space,
        input_refs=body.input_refs,
    )
    if data_space == "synthetic":
        registry = build_synthetic_registry(state.tool_audit_recorder)
    elif _knowledge_search is not None:
        registry = build_real_registry(
            _knowledge_search,
            state.tool_audit_recorder,
            ExperimentDatasetRepository(run_store._persistence_store),
            _live_literature_search(),
            LiteratureLeadRepository(run_store._persistence_store),
        )
    else:
        raise HTTPException(status_code=503, detail="knowledge search storage is unavailable")
    result = registry.execute(request, context)
    state.persist()
    return {
        "request_id": result.request_id,
        "name": result.name,
        "version": result.version,
        "status": result.status,
        "payload": result.payload,
        "source_refs": result.source_refs,
        "data_space": result.data_space,
        "error_code": result.error_code,
    }
