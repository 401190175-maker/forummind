"""Pure projection helpers for native runtime events."""
from __future__ import annotations

import math
from typing import Any, Mapping

from app.agent_runtime.schemas import AgentResult, CandidateStreamEvent, RuntimeEvent
from app.agent_runtime import candidate_buffer
from app.research.contracts import REAL_DATA_SPACES


_RUNTIME_EVENT_TYPES = {
    "run_started", "agent_started", "text_delta", "text_completed", "tool_started",
    "tool_update", "tool_completed", "turn_started", "turn_completed",
    "agent_settled", "agent_failed", "agent_aborted",
}


def validate_runtime_event(event: Mapping[str, Any]) -> dict[str, Any]:
    required = ("event_id", "cursor", "session_id", "invocation_id", "run_id", "group_chat_id", "agent_id", "phase", "type", "payload", "data_space", "timestamp")
    missing = [field for field in required if field not in event]
    if missing:
        raise ValueError(f"runtime event missing fields: {missing}")
    for field in ("event_id", "session_id", "invocation_id", "run_id", "group_chat_id", "agent_id", "phase", "data_space"):
        if not isinstance(event[field], str) or not event[field].strip():
            raise ValueError(f"runtime event {field} must be non-empty text")
    if not isinstance(event["cursor"], int) or event["cursor"] < 1:
        raise ValueError("runtime event cursor is invalid")
    if event["type"] not in _RUNTIME_EVENT_TYPES:
        raise ValueError(f"runtime event type is invalid: {event['type']}")
    if not isinstance(event["payload"], Mapping):
        raise ValueError("runtime event payload must be an object")
    if not isinstance(event["timestamp"], (int, float)) or not math.isfinite(event["timestamp"]):
        raise ValueError("runtime event timestamp is invalid")
    value = dict(event)
    if "task_id" in value and not isinstance(value["task_id"], str):
        raise ValueError("runtime event task_id must be text")
    if "document_scope" in value:
        scope = value["document_scope"]
        if not isinstance(scope, list) or not all(isinstance(item, str) for item in scope):
            raise ValueError("runtime event document_scope must be a list of strings")
    return value


def project_candidate_event(event: Mapping[str, Any]) -> CandidateStreamEvent | None:
    value = validate_runtime_event(event)
    if value["type"] not in {"text_delta", "text_completed"}:
        return None
    payload = value["payload"]
    content = payload.get("content_delta", payload.get("content", ""))
    if not isinstance(content, str):
        raise ValueError("candidate event content must be text")
    return CandidateStreamEvent(
        id=str(value["event_id"]), run_id=str(value["run_id"]),
        agent_id=str(value["agent_id"]), content_delta=content,
        status="completed" if value["type"] == "text_completed" else "streaming",
        data_space=str(value["data_space"]), task_id=str(value.get("task_id", "")),
        document_scope=list(value.get("document_scope", [])),
    )


def settled_result_from_event(event: Mapping[str, Any]) -> AgentResult:
    value = validate_runtime_event(event)
    if value["type"] != "agent_settled":
        raise ValueError("event is not agent_settled")
    raw = value["payload"].get("result")
    if not isinstance(raw, Mapping):
        raise ValueError("settled event lacks result")
    return AgentResult.model_validate(raw)


def project_runtime_event(state: Any, event: Mapping[str, Any] | RuntimeEvent) -> None:
    """Project one trusted runtime event into RunState/candidate-only views."""
    value = event.model_dump(mode="python") if isinstance(event, RuntimeEvent) else validate_runtime_event(event)
    if value["run_id"] != state.run_id or value["group_chat_id"] != state.group_chat_id:
        raise ValueError("runtime event identity mismatch")
    task_context = getattr(state, "task_context", {}) or {}
    expected_task_id = str(getattr(state, "task_id", "") or task_context.get("task_id", "")).strip()
    expected_data_space = str(task_context.get("data_space", "synthetic")).strip()
    expected_documents = [
        str(item).strip()
        for item in task_context.get("allowed_document_ids", task_context.get("document_ids", []))
    ]
    ref_key, ref = _session_ref_for_event(state, value)
    server_owned_start = (
        value["type"] == "run_started"
        and value["event_id"] == f"run-started:{state.run_id}"
        and value["session_id"] == f"server:{state.run_id}"
        and value["invocation_id"] == f"run-started:{state.run_id}"
    )
    if expected_data_space in REAL_DATA_SPACES:
        if not expected_task_id:
            raise ValueError("runtime event task_id is missing from Run scope")
        if value["data_space"] != expected_data_space:
            raise ValueError("runtime event data_space mismatch")
        event_task_id = str(value.get("task_id", "")).strip()
        if not event_task_id:
            raise ValueError("runtime event task_id is missing")
        if event_task_id != expected_task_id:
            raise ValueError("runtime event task_id mismatch")
        raw_scope = value.get("document_scope")
        if raw_scope is None:
            raise ValueError("runtime event document scope is missing")
        if [str(item).strip() for item in raw_scope] != expected_documents:
            raise ValueError("runtime event document scope mismatch")
        bound_agent_ids = {
            str(item.get("agent_id", "")).strip()
            for item in getattr(state, "agent_specs", [])
            if isinstance(item, Mapping)
        }
        bound_agent_ids.update(
            str(agent_id).strip()
            for agent_id in getattr(state, "session_refs", {})
        )
        review_agent = getattr(state, "review_agent_spec", {}) or {}
        if isinstance(review_agent, Mapping):
            bound_agent_ids.add(str(review_agent.get("agent_id", "")).strip())
        postdoc_agent = getattr(state, "postdoc_agent_spec", {}) or {}
        if isinstance(postdoc_agent, Mapping):
            bound_agent_ids.add(str(postdoc_agent.get("agent_id", "")).strip())
        if value["agent_id"] not in bound_agent_ids:
            raise ValueError("runtime event agent identity is not bound to Run")
        if not server_owned_start and (ref is None or ref.invocation_id != value["invocation_id"]):
            raise ValueError("runtime event invocation identity is not bound to Session")
    elif value["data_space"] != "synthetic":
        raise ValueError("runtime event data_space mismatch")
    if ref is not None:
        if (
            ref.session_id != value["session_id"]
            or ref.run_id != value["run_id"]
            or ref.phase != value["phase"]
            or ref.data_space != value["data_space"]
            or (ref.task_id and ref.task_id != str(value.get("task_id", "")))
            or not _same_document_scope(ref.document_scope, value.get("document_scope", []))
        ):
            raise ValueError("runtime event session identity mismatch")
    duplicate = any(
        item.get("event_id") == value.get("event_id")
        or (item.get("session_id") == value.get("session_id") and item.get("cursor") == value.get("cursor"))
        for item in getattr(state, "runtime_events", [])
    )
    if duplicate:
        state.runtime_cursor = max(state.runtime_cursor, value["cursor"])
        return
    state.runtime_cursor = max(state.runtime_cursor, value["cursor"])
    state.runtime_events.append(dict(value))
    if ref is not None:
        state.session_refs[ref_key] = ref.model_copy(
            update={"last_cursor": max(ref.last_cursor, value["cursor"]), "status": "settled" if value["type"] == "agent_settled" else ref.status}
        )
    candidate = project_candidate_event(value)
    if candidate is not None:
        candidate_buffer.append_event(candidate)
    state.persist()


def _session_ref_for_event(state: Any, event: Mapping[str, Any]) -> tuple[str, RuntimeSessionRef | None]:
    """Resolve retries by invocation identity before using the legacy key."""
    agent_id = str(event["agent_id"])
    invocation_id = str(event["invocation_id"])
    for key, ref in getattr(state, "session_refs", {}).items():
        if ref.agent_id == agent_id and ref.invocation_id == invocation_id:
            return key, ref
    ref = getattr(state, "session_refs", {}).get(agent_id)
    return agent_id, ref


def _same_document_scope(left: list[str], right: object) -> bool:
    if not isinstance(right, list):
        return False
    return sorted(str(item).strip() for item in left) == sorted(str(item).strip() for item in right)
