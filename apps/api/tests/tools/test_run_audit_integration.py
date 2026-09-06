from app.orchestration.run_store import RunStore
from app.agent_runtime.schemas import AgentInvocation
from app.tools import build_synthetic_registry
from app.tools.context import build_tool_execution_context
from app.tools.schemas import ToolRequest


def test_run_store_exposes_only_its_own_tool_audit_records() -> None:
    store = RunStore()
    state = store.create("gc-1", "live")
    other = store.create("gc-2", "live")
    context = build_tool_execution_context(AgentInvocation(
        run_id=state.run_id, group_chat_id=state.group_chat_id, cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student", task="read",
    ), runtime_name="pi")
    build_synthetic_registry(store.get_audit_recorder(state.run_id)).execute(
        ToolRequest(request_id="r-1", name="memory.query"), context
    )
    assert len(state.tool_audit_records) == 1
    assert store.list_tool_audit(other.run_id) == []
    assert state.memory.entries() == []
