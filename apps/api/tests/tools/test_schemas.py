import pytest
from pydantic import ValidationError

from app.tools import (
    ToolCallRecord,
    ToolPolicyDecision,
    ToolRequest,
    ToolResult,
    ToolSpec,
)


def test_tool_dtos_capture_read_only_synthetic_contracts() -> None:
    spec = ToolSpec(
        name="memory.query",
        version="1.0",
        description="Read synthetic memory",
        read_only=True,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        allowed_roles=["master_student"],
        allowed_phases=["independent_analysis"],
        data_spaces=["synthetic"],
        result_limits={"max_items": 10, "max_bytes": 4096},
    )
    request = ToolRequest(request_id="req-1", name=spec.name, arguments={"kind": "Claim"})
    result = ToolResult(request_id=request.request_id, name=spec.name, version=spec.version, payload={})
    record = ToolCallRecord(
        record_id="audit-1", request_id=request.request_id, run_id="run-1",
        group_chat_id="gc-1", cycle=1, phase="independent_analysis",
        agent_id="agent-ms-1", role="master_student", runtime="pi",
        tool_name=spec.name, tool_version=spec.version, authorization="allowed",
        status="success", argument_summary={"keys": ["kind"]},
        source_refs=[], result_summary={"items": 0},
        requested_data_space="synthetic", returned_data_space="synthetic",
        policy_version="p2-v1", started_at=1.0, duration_ms=2.0,
    )
    decision = ToolPolicyDecision(allowed=True, reason="allowed", policy_version="p2-v1", allowed_tools=[spec.name])
    assert spec.read_only and request.data_space == "synthetic"
    assert result.status == "ok" and result.data_space == "synthetic"
    assert record.authorization == "allowed" and record.status == "success"
    assert decision.allowed_tools == [spec.name]


def test_tool_dtos_reject_unknown_status_and_empty_identifiers() -> None:
    with pytest.raises(ValidationError):
        ToolResult(request_id="r", name="x", version="1", status="wat", payload={})
    with pytest.raises(ValidationError):
        ToolCallRecord(
            record_id="", request_id="r", run_id="run", group_chat_id="gc",
            cycle=1, phase="p", agent_id="a", role="r", runtime="pi",
            tool_name="x", tool_version="1", authorization="allowed",
            status="success", argument_summary={}, source_refs=[], result_summary={},
            requested_data_space="synthetic", returned_data_space="synthetic",
            policy_version="p2-v1", started_at=0, duration_ms=0,
        )


def test_mutable_dto_defaults_are_isolated() -> None:
    first = ToolRequest(request_id="r1", name="x", arguments={})
    second = ToolRequest(request_id="r2", name="x", arguments={})
    first.input_refs.append("mem-1")
    first.arguments["x"] = 1
    assert second.input_refs == [] and second.arguments == {}
