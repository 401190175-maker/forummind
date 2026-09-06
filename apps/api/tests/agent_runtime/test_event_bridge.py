import pytest

from app.agent_runtime.event_bridge import (
    project_candidate_event,
    project_runtime_event,
    settled_result_from_event,
)
from app.agent_runtime.schemas import RuntimeSessionRef
from app.orchestration.run_store import RunStore


def event(kind="text_delta"):
    return {
        "event_id": "e-1", "cursor": 1, "session_id": "s-1", "invocation_id": "i-1",
        "run_id": "run-1", "group_chat_id": "gc-1", "agent_id": "a-1", "phase": "p",
        "type": kind, "payload": {"content_delta": "candidate"}, "data_space": "synthetic", "timestamp": 1.0,
    }


def test_candidate_projection_does_not_create_formal_memory():
    projected = project_candidate_event(event())
    assert projected is not None
    assert projected.status == "streaming"
    assert projected.content_delta == "candidate"


def test_invalid_identity_shape_is_rejected():
    with pytest.raises(ValueError, match="missing"):
        project_candidate_event({"type": "text_delta"})


def test_settled_projection_requires_result():
    value = event("agent_settled")
    value["payload"] = {"result": {"content": "final", "status": "ok", "agent_id": "a-1"}}
    assert settled_result_from_event(value).content == "final"


def test_real_event_projection_preserves_task_and_document_scope():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
    )
    state.session_refs["a-1"] = RuntimeSessionRef(
        session_id="s-1", group_chat_id="gc-1", run_id=state.run_id,
        agent_id="a-1", phase="independent_analysis",
        data_space="desensitized_real", task_id="task-1", document_scope=["doc-1"],
        invocation_id="i-1",
    )
    value = event("text_delta")
    value.update(
        task_id="task-1", document_scope=["doc-1"],
        run_id=state.run_id, phase="independent_analysis", data_space="desensitized_real",
    )

    project_runtime_event(state, value)

    assert state.runtime_events[0]["task_id"] == "task-1"
    assert state.runtime_events[0]["document_scope"] == ["doc-1"]
    assert state.session_refs["a-1"].last_cursor == 1


def test_server_owned_real_run_started_event_does_not_require_agent_session():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
        agent_specs=[{"agent_id": "a-1", "role": "master_student"}],
    )
    value = event("run_started")
    value.update(
        event_id=f"run-started:{state.run_id}",
        session_id=f"server:{state.run_id}",
        invocation_id=f"run-started:{state.run_id}",
        run_id=state.run_id,
        agent_id="a-1",
        phase="independent_analysis",
        task_id="task-1",
        document_scope=["doc-1"],
        data_space="desensitized_real",
        payload={"status": "running"},
    )

    project_runtime_event(state, value)

    assert state.runtime_events[0]["type"] == "run_started"
    assert state.runtime_events[0]["session_id"] == f"server:{state.run_id}"


def test_server_owned_real_run_started_event_accepts_bound_postdoc_agent():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
        agent_specs=[{"agent_id": "master-1", "role": "master_student"}],
        review_agent_spec={"agent_id": "phd-1", "role": "phd_student"},
        postdoc_agent_spec={"agent_id": "postdoc-1", "role": "postdoc"},
    )

    value = event("run_started")
    value.update(
        event_id=f"run-started:{state.run_id}",
        session_id=f"server:{state.run_id}",
        invocation_id=f"run-started:{state.run_id}",
        run_id=state.run_id,
        agent_id="postdoc-1",
        phase="independent_analysis",
        task_id="task-1",
        document_scope=["doc-1"],
        data_space="desensitized_real",
        payload={"status": "running"},
    )

    project_runtime_event(state, value)

    assert state.runtime_events[0]["agent_id"] == "postdoc-1"


def test_forged_server_run_started_event_requires_agent_session():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
        agent_specs=[{"agent_id": "a-1", "role": "master_student"}],
    )
    value = event("run_started")
    value.update(
        event_id="forged-run-started",
        session_id=f"server:{state.run_id}",
        invocation_id=f"run-started:{state.run_id}",
        run_id=state.run_id,
        agent_id="a-1",
        phase="independent_analysis",
        task_id="task-1",
        document_scope=["doc-1"],
        data_space="desensitized_real",
        payload={"status": "running"},
    )

    with pytest.raises(ValueError, match="invocation identity"):
        project_runtime_event(state, value)
    assert state.runtime_events == []


def test_unbound_real_agent_run_started_event_requires_agent_session():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
        agent_specs=[{"agent_id": "a-1", "role": "master_student"}],
    )
    value = event("run_started")
    value.update(
        event_id="agent-run-started",
        session_id="agent-session",
        invocation_id="agent-invocation",
        run_id=state.run_id,
        agent_id="a-1",
        phase="independent_analysis",
        task_id="task-1",
        document_scope=["doc-1"],
        data_space="desensitized_real",
        payload={"status": "running"},
    )

    with pytest.raises(ValueError, match="invocation identity"):
        project_runtime_event(state, value)
    assert state.runtime_events == []


def test_real_event_projection_rejects_scope_mismatch():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
    )
    value = event("text_delta")
    value.update(
        run_id=state.run_id, task_id="task-1", document_scope=["doc-other"],
        data_space="desensitized_real",
    )

    with pytest.raises(ValueError, match="document scope"):
        project_runtime_event(state, value)


def test_real_event_projection_rejects_unknown_agent():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
        agent_specs=[{"agent_id": "a-1", "role": "master_student"}],
    )
    value = event("text_delta")
    value.update(
        run_id=state.run_id, agent_id="foreign-agent", task_id="task-1",
        document_scope=["doc-1"], data_space="desensitized_real",
    )

    with pytest.raises(ValueError, match="agent identity"):
        project_runtime_event(state, value)


def test_event_projection_updates_the_invocation_specific_retry_session():
    state = RunStore().create("gc-1", "live")
    state.session_refs["a-1"] = RuntimeSessionRef(
        session_id="s-1", group_chat_id="gc-1", run_id=state.run_id,
        agent_id="a-1", phase="independent_analysis", invocation_id="i-1", attempt=1,
    )
    state.session_refs["a-1:attempt-2"] = RuntimeSessionRef(
        session_id="s-2", group_chat_id="gc-1", run_id=state.run_id,
        agent_id="a-1", phase="independent_analysis", invocation_id="i-2", attempt=2,
    )
    value = event("text_delta")
    value.update(
        run_id=state.run_id, session_id="s-2", invocation_id="i-2",
        phase="independent_analysis",
    )

    project_runtime_event(state, value)

    assert state.session_refs["a-1"].last_cursor == 0
    assert state.session_refs["a-1:attempt-2"].last_cursor == 1


def test_real_event_projection_rejects_an_unbound_invocation_on_a_bound_session():
    state = RunStore().create(
        "gc-1", "live", task_id="task-1",
        task_context={
            "task_id": "task-1",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
        },
        agent_specs=[{"agent_id": "a-1", "role": "master_student"}],
    )
    state.session_refs["a-1"] = RuntimeSessionRef(
        session_id="s-1", group_chat_id="gc-1", run_id=state.run_id,
        agent_id="a-1", phase="independent_analysis",
        data_space="desensitized_real", task_id="task-1", document_scope=["doc-1"],
        invocation_id="bound-invocation",
    )
    value = event("text_delta")
    value.update(
        run_id=state.run_id, session_id="s-1", invocation_id="foreign-invocation",
        task_id="task-1", document_scope=["doc-1"], data_space="desensitized_real",
    )

    with pytest.raises(ValueError, match="invocation identity"):
        project_runtime_event(state, value)
    assert state.runtime_events == []

    value.update(invocation_id="bound-invocation", session_id="foreign-session")
    with pytest.raises(ValueError, match="session identity"):
        project_runtime_event(state, value)
    assert state.runtime_events == []
