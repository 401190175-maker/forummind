import pytest

from app.agent_runtime.event_bridge import project_runtime_event
from app.agent_runtime.schemas import RuntimeSessionRef
from app.agent_runtime.candidate_buffer import list_events, reset_buffer
from app.orchestration.run_store import RunStore


def test_streamed_candidate_is_not_memory_until_validation():
    reset_buffer()
    state = RunStore().create("gc-1", "live")
    state.session_refs["agent-ms-1"] = RuntimeSessionRef(
        session_id="s-1", group_chat_id="gc-1", run_id=state.run_id,
        agent_id="agent-ms-1", phase="independent_analysis",
    )
    project_runtime_event(state, {
        "event_id": "e-1", "cursor": 1, "session_id": "s-1", "invocation_id": "i-1",
        "run_id": state.run_id, "group_chat_id": "gc-1", "agent_id": "agent-ms-1",
        "phase": "independent_analysis", "type": "text_delta",
        "payload": {"content_delta": "候选内容"}, "data_space": "synthetic", "timestamp": 1.0,
    })
    assert not any(entry.kind == "Claim" for entry in state.memory.entries())
    assert list_events(state.run_id)[0].content_delta == "候选内容"
    assert state.runtime_cursor == 1


def test_cross_run_runtime_event_is_rejected():
    state = RunStore().create("gc-1", "live")
    with pytest.raises(ValueError, match="identity"):
        project_runtime_event(state, {
            "event_id": "e-1", "cursor": 1, "session_id": "s-1", "invocation_id": "i-1",
            "run_id": "foreign", "group_chat_id": "gc-1", "agent_id": "agent-ms-1",
            "phase": "independent_analysis", "type": "text_delta", "payload": {},
            "data_space": "synthetic", "timestamp": 1.0,
        })
