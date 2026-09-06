import pytest

from app.agent_runtime.schemas import AgentInvocation
from app.tools.context import build_tool_execution_context
from app.tools.policy import authorize_tool, resolve_allowed_tools
from app.tools.schemas import ToolRequest, ToolSpec


def _context(**updates):
    invocation = AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1",
        role="master_student", task="inspect", input_refs=["mem-1"],
    ).model_copy(update=updates)
    return build_tool_execution_context(invocation, runtime_name=updates.get("runtime_name", "pi"))


def _spec(name="memory.query"):
    return ToolSpec(
        name=name, version="1.0", description="read", read_only=True,
        allowed_roles=["master_student"], allowed_phases=["independent_analysis"],
        data_spaces=["synthetic"],
    )


def test_only_pi_master_independent_synthetic_gets_three_tools() -> None:
    decision = resolve_allowed_tools(_context())
    assert decision.allowed
    assert decision.allowed_tools == ["memory.query", "literature.search", "experiment.analyze_demo"]
    for updates in (
        {"runtime_name": "mock"}, {"role": "phd_student"},
        {"phase": "meeting"}, {"data_space": "unknown"},
    ):
        if updates.get("data_space") == "unknown":
            with pytest.raises(ValueError):
                _context(**updates)
            continue
        assert not resolve_allowed_tools(_context(**updates)).allowed


def test_authorize_rejects_unknown_scope_and_refs_without_running_code() -> None:
    context = _context()
    specs = [_spec()]
    assert authorize_tool(ToolRequest(request_id="r", name="unknown"), context, specs).reason == "not_found"
    assert authorize_tool(
        ToolRequest(request_id="r", name="memory.query", input_refs=["mem-foreign"]), context, specs
    ).reason == "input_ref_forbidden"
    assert authorize_tool(
        ToolRequest(request_id="r", name="memory.query", data_space="real"), context, specs
    ).reason == "data_space_mismatch"


def test_request_arguments_cannot_expand_server_context() -> None:
    context = _context()
    decision = authorize_tool(
        ToolRequest(
            request_id="r", name="memory.query",
            arguments={"run_id": "run-other", "agent_id": "agent-other", "role": "phd_student"},
        ),
        context, [_spec()],
    )
    assert decision.allowed
    assert decision.allowed_tools == ["memory.query"]
