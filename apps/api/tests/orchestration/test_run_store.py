"""RunStore / RunStep / RunState 单元测试。"""
from app.orchestration.run_store import RunStep, RunStore
from app.agent_runtime.schemas import AgentInvocation, RuntimeSessionRef
from app.tools import build_synthetic_registry
from app.tools.context import build_tool_execution_context
from app.tools.schemas import ToolRequest
from app.storage.sqlite_store import SQLiteStore


def test_run_store_create_and_get():
    store = RunStore()
    s = store.create("gc-1", "replay")
    assert s.run_id.startswith("run-")
    assert s.cycle == 1
    assert s.status == "running"
    assert store.get(s.run_id) is s


def test_run_store_reset():
    store = RunStore()
    store.create("gc-1", "replay")
    store.reset()
    assert len(store._runs) == 0


def test_run_step_frozen():
    step = RunStep(id="step-1", phase="independent_analysis", kind="claim",
                   actor="agent-ms-1", content="x", payload={}, timestamp=1.0)
    assert step.phase == "independent_analysis"


def test_run_audit_is_bound_to_state_and_not_memory():
    store = RunStore()
    first = store.create("gc-1", "live")
    second = store.create("gc-2", "live")
    context = build_tool_execution_context(AgentInvocation(
        run_id=first.run_id, group_chat_id=first.group_chat_id, cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student", task="read",
    ), runtime_name="pi")
    registry = build_synthetic_registry(store.get_audit_recorder(first.run_id))
    registry.execute(ToolRequest(request_id="r-1", name="memory.query"), context)
    assert len(store.list_tool_audit(first.run_id)) == 1
    assert store.list_tool_audit(second.run_id) == []
    assert first.memory.entries() == []
    store.reset()
    assert store.list_tool_audit(first.run_id) == []


def test_runtime_session_table_recovers_retry_identity_after_restart(tmp_path):
    database = SQLiteStore(tmp_path / "runtime-sessions.db")
    database.initialize()
    first_store = RunStore(database)
    state = first_store.create("gc-1", "live")
    ref = RuntimeSessionRef(
        session_id="session-retry-2",
        group_chat_id=state.group_chat_id,
        run_id=state.run_id,
        agent_id="agent-ms-2",
        phase="independent_analysis",
        invocation_id="invocation-retry-2",
        attempt=2,
        retry_of="invocation-failed-1",
    )
    first_store.save_runtime_session(ref, session_scope="gc-1/run-1/agent-ms-2")
    database.close()

    recovered = SQLiteStore(tmp_path / "runtime-sessions.db")
    recovered.initialize()
    state_after_restart = RunStore(recovered).resume_run(state.run_id)

    assert state_after_restart is not None
    recovered_ref = state_after_restart.session_refs["agent-ms-2:attempt-2"]
    assert recovered_ref.invocation_id == "invocation-retry-2"
    assert recovered_ref.attempt == 2
    assert recovered_ref.retry_of == "invocation-failed-1"
