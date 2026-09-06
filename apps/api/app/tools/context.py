"""Minimal immutable context handed to a tool handler."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.agent_runtime.schemas import AgentInvocation
from app.tasks.schemas import DatasetVersionRef

SUPPORTED_DATA_SPACES = {"synthetic", "real", "desensitized_real"}
REAL_DATA_SPACES = {"real", "desensitized_real"}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _snapshot(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    fields = ("id", "kind", "payload", "version", "supersedes", "created_at", "object_key", "data_space")
    return {field: getattr(value, field) for field in fields if hasattr(value, field)}


@dataclass(frozen=True)
class ToolLimits:
    max_calls: int = 3
    max_items: int = 10
    max_result_bytes: int = 8192
    deadline_seconds: float = 30.0
    max_content_chars: int = 12000

    def __post_init__(self) -> None:
        if self.max_calls < 1 or self.max_items < 1 or self.max_result_bytes < 1 or self.deadline_seconds <= 0:
            raise ValueError("tool limits must be positive")


@dataclass(frozen=True)
class ToolExecutionContext:
    runtime_name: str
    run_id: str
    group_chat_id: str
    cycle: int
    phase: str
    agent_id: str
    role: str
    data_space: str
    task_id: str
    allowed_document_ids: tuple[str, ...]
    allowed_dataset_refs: tuple[DatasetVersionRef, ...]
    allowed_source_data_spaces: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    input_refs: tuple[str, ...]
    memory_entries: tuple[Mapping[str, Any], ...]
    literature_leads: tuple[Mapping[str, Any], ...]
    experiment_view: Mapping[str, Any]
    limits: ToolLimits


def build_tool_execution_context(
    invocation: AgentInvocation,
    *,
    runtime_name: str,
    memory_entries: list[Any] | tuple[Any, ...] | None = None,
    literature_leads: list[Any] | tuple[Any, ...] | None = None,
    experiment_view: Mapping[str, Any] | None = None,
    limits: ToolLimits | Mapping[str, Any] | None = None,
    task_id: str | None = None,
    allowed_document_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    allowed_dataset_refs: list[DatasetVersionRef] | tuple[DatasetVersionRef, ...] | None = None,
    allowed_source_data_spaces: list[str] | tuple[str, ...] | set[str] | None = None,
) -> ToolExecutionContext:
    required = {
        "run_id": invocation.run_id,
        "group_chat_id": invocation.group_chat_id,
        "phase": invocation.phase,
        "agent_id": invocation.agent_id,
        "role": invocation.role,
        "runtime_name": runtime_name,
    }
    for field, value in required.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
    if invocation.cycle is None or invocation.cycle < 1:
        raise ValueError("cycle is required")
    data_space = invocation.data_space.strip()
    if data_space not in SUPPORTED_DATA_SPACES:
        raise ValueError("data_space is unsupported")
    invocation_context = invocation.context if isinstance(invocation.context, Mapping) else {}
    resolved_task_id = task_id if task_id is not None else invocation_context.get("task_id", "")
    resolved_documents = (
        allowed_document_ids
        if allowed_document_ids is not None
        else invocation_context.get("allowed_document_ids", invocation_context.get("document_ids", ()))
    )
    if not isinstance(resolved_task_id, str) or (data_space in REAL_DATA_SPACES and not resolved_task_id.strip()):
        raise ValueError("task_id is required for real data")
    if not isinstance(resolved_documents, (list, tuple, set)):
        raise ValueError("allowed_document_ids must be a sequence")
    normalized_documents = tuple(str(item).strip() for item in resolved_documents)
    if any(not item for item in normalized_documents) or len(set(normalized_documents)) != len(normalized_documents):
        raise ValueError("allowed_document_ids must contain unique non-empty strings")
    resolved_datasets = (
        allowed_dataset_refs
        if allowed_dataset_refs is not None
        else invocation_context.get("allowed_dataset_refs", invocation_context.get("dataset_refs", ()))
    )
    if not isinstance(resolved_datasets, (list, tuple)):
        raise ValueError("allowed_dataset_refs must be a sequence")
    normalized_datasets = tuple(DatasetVersionRef.model_validate(item) for item in resolved_datasets)
    dataset_keys = [(item.dataset_id, item.version) for item in normalized_datasets]
    if len(set(dataset_keys)) != len(dataset_keys):
        raise ValueError("allowed_dataset_refs must contain unique dataset versions")
    resolved_source_spaces = (
        allowed_source_data_spaces
        if allowed_source_data_spaces is not None
        else invocation_context.get(
            "allowed_source_data_spaces",
            (data_space, "verifiable_public") if data_space in REAL_DATA_SPACES else (data_space,),
        )
    )
    if not isinstance(resolved_source_spaces, (list, tuple, set)):
        raise ValueError("allowed_source_data_spaces must be a sequence")
    normalized_source_spaces = tuple(str(item).strip() for item in resolved_source_spaces)
    if any(not item for item in normalized_source_spaces) or len(set(normalized_source_spaces)) != len(normalized_source_spaces):
        raise ValueError("allowed_source_data_spaces must contain unique non-empty strings")
    if limits is None:
        resolved_limits = ToolLimits()
    elif isinstance(limits, ToolLimits):
        resolved_limits = limits
    else:
        resolved_limits = ToolLimits(**dict(limits))
    return ToolExecutionContext(
        runtime_name=runtime_name.strip(), run_id=invocation.run_id.strip(),
        group_chat_id=invocation.group_chat_id.strip(), cycle=invocation.cycle,
        phase=invocation.phase.strip(), agent_id=invocation.agent_id.strip(),
        role=invocation.role.strip(), data_space=data_space,
        task_id=resolved_task_id.strip(), allowed_document_ids=normalized_documents,
        allowed_dataset_refs=normalized_datasets,
        allowed_source_data_spaces=normalized_source_spaces,
        allowed_tools=tuple(str(item).strip() for item in invocation.allowed_tools if str(item).strip()),
        input_refs=tuple(_freeze(list(invocation.input_refs))),
        memory_entries=tuple(_freeze(_snapshot(item)) for item in (memory_entries or ())),
        literature_leads=tuple(_freeze(_snapshot(item)) for item in (literature_leads or ())),
        experiment_view=_freeze(_snapshot(experiment_view or {})),
        limits=resolved_limits,
    )
