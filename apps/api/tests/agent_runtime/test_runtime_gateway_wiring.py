"""Regression tests for server-owned runtime identity checks."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.agent_runtime.schemas import RuntimeSessionRef
from app.api import runtime_internal
from app.orchestration.run_store import RunStore


def test_gateway_rejects_known_agent_that_is_not_current_invocation(monkeypatch):
    store = RunStore()
    state = store.create(
        "gc-gateway",
        "live",
        agent_specs=[
            {"agent_id": "agent-ms-1", "role": "master_student", "allowed_tools": ["memory.query"]},
            {"agent_id": "agent-ms-2", "role": "master_student", "allowed_tools": ["memory.query"]},
        ],
    )
    state.current_agent_id = "agent-ms-1"
    state.current_phase = "independent_analysis"
    state.current_invocation_id = "inv-current"
    state.session_refs["agent-ms-1"] = RuntimeSessionRef(
        session_id="session-current",
        group_chat_id=state.group_chat_id,
        run_id=state.run_id,
        agent_id="agent-ms-1",
        phase="independent_analysis",
        invocation_id="inv-current",
    )
    monkeypatch.setattr(runtime_internal, "run_store", store)
    monkeypatch.setenv("PI_RUNTIME_TOKEN", "secret")

    body = runtime_internal.RuntimeToolCallRequest(
        request_id="req-foreign-agent",
        name="memory.query",
        arguments={"query": "x"},
        run_id=state.run_id,
        group_chat_id=state.group_chat_id,
        agent_id="agent-ms-2",
        data_space="synthetic",
    )

    with pytest.raises(HTTPException, match="current agent"):
        runtime_internal.execute_runtime_tool(body, "secret")


def test_gateway_resolves_frozen_postdoc_spec_before_policy():
    store = RunStore()
    state = store.create(
        "gc-gateway-postdoc",
        "live",
        agent_specs=[{"agent_id": "agent-ms-1", "role": "master_student"}],
        postdoc_agent_spec={
            "agent_id": "agent-postdoc-1",
            "role": "postdoc",
            "allowed_tools": ["memory.query"],
        },
    )
    state.current_agent_id = "agent-postdoc-1"
    state.current_phase = "postdoc_exchange"
    state.current_invocation_id = "inv-postdoc"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runtime_internal, "run_store", store)
    monkeypatch.setenv("PI_RUNTIME_TOKEN", "secret")
    try:
        body = runtime_internal.RuntimeToolCallRequest(
            request_id="req-postdoc",
            name="memory.query",
            arguments={"query": "x"},
            run_id=state.run_id,
            group_chat_id=state.group_chat_id,
            agent_id="agent-postdoc-1",
            data_space="synthetic",
        )
        result = runtime_internal.execute_runtime_tool(body, "secret")
    finally:
        monkeypatch.undo()

    assert result["status"] == "denied"


def test_gateway_rejects_stale_attempt_identity(monkeypatch):
    store = RunStore()
    state = store.create(
        "gc-gateway-attempt",
        "live",
        agent_specs=[{"agent_id": "agent-ms-1", "role": "master_student", "allowed_tools": ["memory.query"]}],
    )
    state.current_agent_id = "agent-ms-1"
    state.current_phase = "independent_analysis"
    state.current_invocation_id = "inv-attempt-2"
    state.agent_attempts["agent-ms-1"] = 2
    monkeypatch.setattr(runtime_internal, "run_store", store)
    monkeypatch.setenv("PI_RUNTIME_TOKEN", "secret")

    body = runtime_internal.RuntimeToolCallRequest(
        request_id="req-stale-attempt",
        name="memory.query",
        arguments={"query": "x"},
        run_id=state.run_id,
        group_chat_id=state.group_chat_id,
        agent_id="agent-ms-1",
        invocation_id="inv-attempt-2",
        attempt=1,
        data_space="synthetic",
    )

    with pytest.raises(HTTPException, match="attempt identity"):
        runtime_internal.execute_runtime_tool(body, "secret")


def test_gateway_uses_server_current_phase_for_tool_policy(monkeypatch):
    store = RunStore()
    state = store.create(
        "gc-gateway-phase",
        "live",
        agent_specs=[
            {
                "agent_id": "agent-ms-1",
                "role": "master_student",
                "allowed_tools": ["memory.query"],
            }
        ],
    )
    state.phase = "independent_analysis"
    state.current_phase = "review_gate"
    state.current_agent_id = "agent-ms-1"
    monkeypatch.setattr(runtime_internal, "run_store", store)
    monkeypatch.setenv("PI_RUNTIME_TOKEN", "secret")

    body = runtime_internal.RuntimeToolCallRequest(
        request_id="req-current-phase",
        name="memory.query",
        arguments={"query": "x"},
        run_id=state.run_id,
        group_chat_id=state.group_chat_id,
        agent_id="agent-ms-1",
        data_space="synthetic",
    )

    result = runtime_internal.execute_runtime_tool(body, "secret")

    assert result["status"] == "denied"
    assert result["error_code"] == "phase_not_allowed"
    assert state.tool_audit_records[-1].phase == "review_gate"
