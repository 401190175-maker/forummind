from app.agent_runtime.schemas import AgentInvocation
from app.tools.context import build_tool_execution_context
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest
from app.tools.synthetic import register_memory_tool


def _ctx():
    return build_tool_execution_context(AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student",
        task="inspect", input_refs=["mem-1"],
    ), runtime_name="pi", memory_entries=[
        {"id": "mem-1", "kind": "Claim", "object_key": "agent-ms-1", "version": 1,
         "supersedes": None, "payload": {"statement": "pore structure"}, "data_space": "synthetic"},
        {"id": "mem-2", "kind": "Decision", "object_key": None, "version": 1,
         "supersedes": None, "payload": {"option": "returned"}, "data_space": "synthetic"},
    ])


def test_memory_query_returns_scoped_read_only_summary_without_mutation() -> None:
    registry = ToolRegistry()
    register_memory_tool(registry)
    before = len(_ctx().memory_entries)
    result = registry.execute(ToolRequest(request_id="r-1", name="memory.query", arguments={"kind": "Claim"}), _ctx())
    assert result.status == "ok"
    assert result.payload["items"][0]["id"] == "mem-1"
    assert "read-only" in result.boundary_notes
    assert len(_ctx().memory_entries) == before
    assert registry.audit("run-1")[0].status == "success"


def test_memory_query_rejects_unknown_kind_and_forbidden_ref() -> None:
    registry = ToolRegistry()
    register_memory_tool(registry)
    unknown = registry.execute(ToolRequest(request_id="r-2", name="memory.query", arguments={"kind": "Unknown"}), _ctx())
    assert unknown.status == "error" and unknown.error_code == "invalid_arguments"
    forbidden = registry.execute(ToolRequest(request_id="r-3", name="memory.query", input_refs=["mem-2"]), _ctx())
    assert forbidden.status == "denied" and forbidden.error_code == "input_ref_forbidden"
