"""Server-owned policy separation between Replay and real research tools."""

from app.agent_runtime.schemas import AgentInvocation
from app.tools import build_synthetic_registry
from app.tools.context import build_tool_execution_context
from app.tools.policy import resolve_allowed_tools


def test_real_context_exposes_only_knowledge_search():
    context = build_tool_execution_context(AgentInvocation(
        run_id="run-1", group_chat_id="group-a", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student",
        task="inspect", allowed_tools=["knowledge.search"], data_space="real",
        context={"task_id": "task-a", "allowed_document_ids": ["doc-a"]},
    ), runtime_name="pi")

    decision = resolve_allowed_tools(context)

    assert decision.allowed
    assert decision.allowed_tools == ["knowledge.search"]
    assert "memory.query" not in decision.allowed_tools


def test_synthetic_registry_stays_replay_only():
    registry = build_synthetic_registry()

    assert set(registry._specs) == {
        "memory.query", "literature.search", "experiment.analyze_demo",
    }
    assert all(spec.data_spaces == ["synthetic"] for spec in registry._specs.values())
