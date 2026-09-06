import pytest

from app.agent_runtime.schemas import AgentInvocation
from app.tools.context import build_tool_execution_context
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest, ToolResult, ToolSpec


def _ctx():
    return build_tool_execution_context(AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1",
        role="master_student", task="read", input_refs=["mem-1"],
    ), runtime_name="pi")


def _spec(name="memory.query"):
    return ToolSpec(name=name, version="1.0", description="read", read_only=True,
                    allowed_roles=["master_student"], allowed_phases=["independent_analysis"],
                    data_spaces=["synthetic"])


def test_registry_registers_executes_and_audits_success() -> None:
    registry = ToolRegistry()
    registry.register(_spec(), lambda request, context: ToolResult(
        request_id=request.request_id, name=request.name, version="1.0", payload={"items": 1},
    ))
    result = registry.execute(ToolRequest(request_id="r-1", name="memory.query"), _ctx())
    assert result.status == "ok" and result.payload == {"items": 1}
    assert registry.audit("run-1")[0].status == "success"


def test_registry_rejects_duplicate_and_unknown_without_running_handler() -> None:
    registry = ToolRegistry()
    called = []
    registry.register(_spec(), lambda request, context: called.append(1))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_spec(), lambda request, context: None)
    result = registry.execute(ToolRequest(request_id="r-2", name="unknown"), _ctx())
    assert result.status == "denied" and result.error_code == "not_found"
    assert called == []
    assert registry.audit("run-1")[0].authorization == "denied"


def test_registry_normalizes_handler_errors_and_bad_data_space() -> None:
    registry = ToolRegistry()
    registry.register(_spec(), lambda request, context: (_ for _ in ()).throw(RuntimeError("boom")))
    error = registry.execute(ToolRequest(request_id="r-3", name="memory.query"), _ctx())
    assert error.status == "error" and error.error_code == "tool_error"
    registry = ToolRegistry()
    registry.register(_spec(), lambda request, context: ToolResult(
        request_id=request.request_id, name=request.name, version="1.0", data_space="real",
    ))
    bad = registry.execute(ToolRequest(request_id="r-4", name="memory.query"), _ctx())
    assert bad.status == "error" and bad.error_code == "data_space_mismatch"
