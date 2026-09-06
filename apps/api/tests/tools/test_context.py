import pytest

from app.agent_runtime.schemas import AgentInvocation
from app.tools.context import ToolExecutionContext, build_tool_execution_context


def _invocation() -> AgentInvocation:
    return AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1",
        role="master_student", task="inspect", input_refs=["mem-1"],
        data_space="synthetic",
    )


def test_context_freezes_scoped_snapshots_and_limits() -> None:
    memory = [{"id": "mem-1", "kind": "Claim", "payload": {"text": "x"}}]
    leads = [{"local_key": "lit-1", "title": "lead"}]
    experiment = {"rows": [{"condition": "A"}]}
    ctx = build_tool_execution_context(
        _invocation(), runtime_name="pi", memory_entries=memory,
        literature_leads=leads, experiment_view=experiment,
        limits={"max_calls": 2, "max_items": 5, "max_result_bytes": 1000, "deadline_seconds": 3},
    )
    memory[0]["payload"]["text"] = "changed"
    leads.append({"local_key": "lit-2"})
    experiment["rows"].append({"condition": "B"})
    assert isinstance(ctx, ToolExecutionContext)
    assert ctx.memory_entries[0]["payload"]["text"] == "x"
    assert len(ctx.literature_leads) == 1
    assert len(ctx.experiment_view["rows"]) == 1
    assert ctx.input_refs == ("mem-1",) and ctx.limits.max_calls == 2
    with pytest.raises(TypeError):
        ctx.experiment_view["rows"] = ()  # type: ignore[index]


def test_context_rejects_missing_scope_or_unsupported_data_space() -> None:
    with pytest.raises(ValueError, match="run_id"):
        build_tool_execution_context(_invocation().model_copy(update={"run_id": ""}), runtime_name="pi")
    with pytest.raises(ValueError, match="data_space"):
        build_tool_execution_context(_invocation().model_copy(update={"data_space": "unknown"}), runtime_name="pi")
