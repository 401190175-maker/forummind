from app.agent_runtime.schemas import AgentInvocation
from app.tools.context import build_tool_execution_context
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest
from app.tools.synthetic import register_literature_tool


def _ctx():
    return build_tool_execution_context(AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student",
        task="search",
    ), runtime_name="pi", literature_leads=[
        {"local_key": "lit-1", "title": "Pore structure and strength", "summary": "pore ratio", "status": "lead", "note": "synthetic"},
        {"local_key": "lit-2", "title": "Slurry foam", "summary": "mixing", "status": "pending", "note": "synthetic"},
    ])


def test_literature_search_is_deterministic_and_non_evidence() -> None:
    registry = ToolRegistry()
    register_literature_tool(registry)
    request = ToolRequest(request_id="r-1", name="literature.search", arguments={"query": "pore", "limit": 1})
    result = registry.execute(request, _ctx())
    assert result.status == "ok" and len(result.payload["items"]) == 1
    assert result.payload["items"][0]["local_key"] == "lit-1"
    assert "non-evidence" in result.boundary_notes
    assert result.payload["items"][0]["status"] == "lead"


def test_literature_search_rejects_invalid_status_and_dynamic_source() -> None:
    registry = ToolRegistry()
    register_literature_tool(registry)
    invalid = registry.execute(ToolRequest(request_id="r-2", name="literature.search", arguments={"status": "verified"}), _ctx())
    assert invalid.status == "error" and invalid.error_code == "invalid_arguments"
    dynamic = registry.execute(ToolRequest(request_id="r-3", name="literature.search", arguments={"url": "https://example.com"}), _ctx())
    assert dynamic.status == "error" and dynamic.error_code == "invalid_arguments"
