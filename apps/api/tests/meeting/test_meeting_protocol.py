"""Formal meeting role, order, and provenance contract tests."""

import pytest

from app.meeting.protocol import (
    MeetingProtocolError,
    build_formal_meeting_events,
    build_task_scoped_meeting_events,
    validate_meeting_stream,
)
from app.meeting.service import MeetingEvent
from app.orchestration.run_store import RunState, RunStep


MASTER_IDS = ["agent-ms-1", "agent-ms-2", "agent-ms-3"]


def _state(*, mode: str = "live") -> RunState:
    return RunState(
        run_id="run-protocol",
        group_chat_id="group-protocol",
        mode=mode,
        status="awaiting_decision",
        phase="meeting",
        cycle=1,
        agent_specs=[
            {"agent_id": agent_id, "role": "master_student"}
            for agent_id in MASTER_IDS
        ],
    )


def _with_master_inputs(state: RunState) -> RunState:
    for index, agent_id in enumerate(MASTER_IDS, start=1):
        step_id = f"step-claim-{index}"
        artifact_id = f"artifact:{agent_id}"
        state.steps.append(
            RunStep(
                id=step_id,
                phase="independent_analysis",
                kind="claim",
                actor=agent_id,
                content=f"{agent_id} 的独立判断",
                payload={"source": "live"},
                timestamp=float(index),
            )
        )
        state.artifacts.append(
            {
                "artifact_id": artifact_id,
                "agent_id": agent_id,
                "artifact_type": "master_research_markdown",
                "filename": f"{agent_id}.md",
                "content": f"# {agent_id}",
            }
        )
    return state


def _event(
    *,
    actor_id: str,
    actor_role: str,
    kind: str,
    source: str = "live",
    source_refs: list[str] | None = None,
    sequence: int = 0,
) -> MeetingEvent:
    return MeetingEvent(
        id=f"event-{sequence or kind}",
        run_id="run-protocol",
        actor_id=actor_id,
        actor_role=actor_role,
        kind=kind,
        content=kind,
        timestamp=float(sequence or 1),
        source_refs=source_refs or [],
        source=source,
        sequence=sequence,
    )


def test_formal_meeting_projects_one_markdown_report_per_master() -> None:
    state = _with_master_inputs(_state())

    events = build_formal_meeting_events(state)

    assert [event.kind for event in events] == ["master_report"] * 3
    assert [event.actor_id for event in events] == MASTER_IDS
    assert all(
        any(ref == f"artifact:{event.actor_id}" for ref in event.source_refs)
        for event in events
    )
    assert all(event.actor_role != "phd_student" for event in events)


def test_formal_meeting_requires_each_master_markdown_report() -> None:
    state = _with_master_inputs(_state())
    state.artifacts.pop()

    with pytest.raises(MeetingProtocolError, match="Markdown"):
        build_formal_meeting_events(state)


def test_phd_report_is_rejected_from_formal_meeting() -> None:
    state = _with_master_inputs(_state())
    events = build_formal_meeting_events(state)
    events.append(
        _event(
            actor_id="agent-phd-1",
            actor_role="phd_student",
            kind="master_report",
            source_refs=["step-claim-1", "artifact:agent-ms-1"],
            sequence=4,
        )
    )

    with pytest.raises(MeetingProtocolError, match="博士"):
        validate_meeting_stream(events, state)


def test_postdoc_response_requires_a_prior_scoped_request() -> None:
    state = _with_master_inputs(_state())
    events = build_formal_meeting_events(state)
    state.steps.append(
        RunStep(
            id="step-postdoc-response",
            phase="postdoc_exchange",
            kind="in_scope_answer",
            actor="agent-postdoc-1",
            content="回答",
            payload={},
            timestamp=4.0,
        )
    )
    events.append(
        _event(
            actor_id="agent-postdoc-1",
            actor_role="postdoc",
            kind="postdoc_response",
            source_refs=["step-postdoc-response"],
            sequence=4,
        )
    )

    with pytest.raises(MeetingProtocolError, match="request"):
        validate_meeting_stream(events, state)


def test_pi_decision_requires_all_master_reports() -> None:
    state = _with_master_inputs(_state())
    events = build_formal_meeting_events(state)[:2]
    events.append(
        _event(
            actor_id="PI",
            actor_role="pi",
            kind="decision",
            source="pi",
            source_refs=["step-pi-decision"],
            sequence=3,
        )
    )
    state.steps.append(
        RunStep(
            id="step-pi-decision",
            phase="meeting",
            kind="decision",
            actor="PI",
            content="退回",
            payload={},
            timestamp=4.0,
        )
    )

    with pytest.raises(MeetingProtocolError, match="所有硕士"):
        validate_meeting_stream(events, state)


def test_pi_event_must_be_emitted_by_pi() -> None:
    state = _with_master_inputs(_state())
    events = build_formal_meeting_events(state)
    events.append(
        _event(
            actor_id="agent-postdoc-1",
            actor_role="postdoc",
            kind="message",
            source="pi",
            source_refs=["pi:message"],
            sequence=4,
        )
    )

    with pytest.raises(MeetingProtocolError, match="PI"):
        validate_meeting_stream(events, state)


def test_task_scoped_projection_keeps_candidate_review_and_suggestion_provenance() -> None:
    state = RunState(
        run_id="run-task-protocol",
        group_chat_id="group-protocol",
        mode="live",
        status="awaiting_review",
        phase="awaiting_review",
        cycle=1,
        task_id="task-protocol",
        agent_specs=[
            {"agent_id": agent_id, "role": "master_student"}
            for agent_id in MASTER_IDS
        ],
        review_agent_spec={"agent_id": "agent-phd-1", "role": "phd_student"},
        postdoc_agent_spec={"agent_id": "agent-postdoc-1", "role": "postdoc"},
        review_result={"disposition": "approved"},
        postdoc_result={"summary": "综合候选"},
        pi_suggestion={"option": "pending", "reason": "等待 PI"},
        task_context={
            "task_id": "task-protocol",
            "completion_mode": "candidate_review",
            "data_space": "desensitized_real",
        },
    )
    for index, agent_id in enumerate(MASTER_IDS, start=1):
        state.steps.append(
            RunStep(
                id=f"step-candidate-{index}",
                phase="independent_analysis",
                kind="candidate",
                actor=agent_id,
                content=f"{agent_id} 候选",
                payload={"source": "live", "candidate_id": f"candidate-{index}"},
                timestamp=float(index),
            )
        )
    for index, kind in enumerate(
        ("counterexample", "falsification_condition", "missing_observation"),
        start=1,
    ):
        state.steps.append(
            RunStep(
                id=f"step-review-{index}",
                phase="review_gate",
                kind="review_opinion",
                actor="agent-phd-1",
                content=kind,
                payload={"source": "live", "kind": kind},
                timestamp=3.0 + index,
            )
        )
    state.steps.extend(
        [
            RunStep(
                id="step-postdoc-request",
                phase="postdoc_exchange",
                kind="request",
                actor="agent-postdoc-1",
                content="专业请求",
                payload={"source": "live"},
                timestamp=7.0,
            ),
            RunStep(
                id="step-postdoc-synthesis",
                phase="postdoc_exchange",
                kind="synthesis",
                actor="agent-postdoc-1",
                content="综合候选",
                payload={"source": "live"},
                timestamp=8.0,
            ),
            RunStep(
                id="step-suggestion",
                phase="postdoc_exchange",
                kind="suggested_decision",
                actor="system",
                content="等待 PI",
                payload={"source": "live", "source_refs": ["step-postdoc-synthesis"]},
                timestamp=9.0,
            ),
        ]
    )

    events = build_task_scoped_meeting_events(state)

    assert [event.kind for event in events] == [
        "candidate_report",
        "candidate_report",
        "candidate_report",
        "review_gate",
        "review_gate",
        "review_gate",
        "postdoc_request",
        "postdoc_response",
        "suggested_decision",
    ]
    assert all(event.source == "live" for event in events)
    assert all(event.source_refs for event in events)
    assert [event.actor_id for event in events[:3]] == MASTER_IDS
    assert all(event.actor_role == "phd_student" for event in events[3:6])
    assert not any(event.kind in {"decision", "final_decision"} for event in events)
