from app.agent_runtime.schemas import AgentInvocation
from app.tools.context import build_tool_execution_context
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest
from app.tools.synthetic import register_experiment_tool


def _ctx(view):
    return build_tool_execution_context(AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student",
        task="analyze",
    ), runtime_name="pi", experiment_view=view)


def test_experiment_analysis_is_deterministic_and_causal_boundary_safe() -> None:
    registry = ToolRegistry()
    register_experiment_tool(registry)
    view = {"plan": {"sample_chain": "A -> B", "measurements": ["strength"]},
            "results": {"rows": [{"condition": "high", "strength_mpa": 3.2}], "source": "demo"},
            "hypothesis_updates": []}
    result = registry.execute(ToolRequest(request_id="r-1", name="experiment.analyze_demo", arguments={"mode": "summary"}), _ctx(view))
    assert result.status == "ok"
    assert result.payload["support_assessment"] in {"supports", "weakened", "inconclusive"}
    assert "causal" in " ".join(result.boundary_notes)
    assert "证明因果" not in str(result.payload)


def test_experiment_analysis_reports_indeterminate_when_result_missing() -> None:
    registry = ToolRegistry()
    register_experiment_tool(registry)
    result = registry.execute(ToolRequest(request_id="r-2", name="experiment.analyze_demo"), _ctx({"plan": None, "results": None}))
    assert result.status == "ok"
    assert result.payload["support_assessment"] == "inconclusive"
    assert "待补证" in " ".join(result.boundary_notes)
