from app.agent_runtime.schemas import RuntimeSessionRef
from app.orchestration.run_store import RunStore


def test_run_state_persists_isolated_session_refs():
    store = RunStore()
    state = store.create("gc-1", "live")
    state.session_refs["agent-ms-1"] = RuntimeSessionRef(
        session_id="s-1", group_chat_id="gc-1", run_id=state.run_id,
        agent_id="agent-ms-1", phase=state.phase,
    )
    state.persist()
    assert set(state.session_refs) == {"agent-ms-1"}
    assert state.session_refs["agent-ms-1"].group_chat_id == state.group_chat_id
