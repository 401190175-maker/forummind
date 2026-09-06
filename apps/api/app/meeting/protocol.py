"""Formal meeting protocol and provenance validation.

The protocol deliberately keeps the PhD outside the meeting report stream:
the PhD is a pre-meeting quality gate, while every master presents its own
persisted Markdown artifact and the PI owns the final decision boundary.
"""

from __future__ import annotations

from collections.abc import Iterable


class MeetingProtocolError(ValueError):
    """A formal meeting event stream violates the documented protocol."""


def _role(value: object) -> str:
    return str(getattr(value, "value", value))


def _step_ids(run_state: object) -> set[str]:
    return {str(getattr(step, "id", "")) for step in getattr(run_state, "steps", [])}


def _artifacts(run_state: object) -> dict[str, dict]:
    return {
        str(item.get("artifact_id")): item
        for item in getattr(run_state, "artifacts", [])
        if isinstance(item, dict) and item.get("artifact_id")
    }


def _markdown_ref(ref: str) -> bool:
    normalized = ref.lower()
    return normalized.endswith(".md") or "artifact" in normalized


def _masters(run_state: object) -> list[str]:
    specs = getattr(run_state, "agent_specs", [])
    configured = [
        str(spec.get("agent_id"))
        for spec in specs
        if _role(spec.get("role", "")) == "master_student"
        and str(spec.get("agent_id", "")).strip()
    ]
    if configured:
        return configured
    return [
        str(getattr(step, "actor", ""))
        for step in getattr(run_state, "steps", [])
        if getattr(step, "phase", "") == "independent_analysis"
        and getattr(step, "kind", "") == "claim"
        and str(getattr(step, "actor", "")).strip()
        and str(getattr(step, "actor", "")).startswith("agent-ms")
    ]


def validate_meeting_event(
    event: object, *, previous: list[object], run_state: object
) -> None:
    """Validate one event against its RunStep provenance and prior events."""
    source = str(getattr(event, "source", ""))
    actor_role = _role(getattr(event, "actor_role", ""))
    kind = str(getattr(event, "kind", ""))
    refs = [str(ref) for ref in getattr(event, "source_refs", [])]
    state_mode = str(getattr(run_state, "mode", ""))
    step_ids = _step_ids(run_state)
    artifacts = _artifacts(run_state)

    if source not in {"live", "scenario", "pi"}:
        raise MeetingProtocolError(f"unknown meeting event source: {source}")
    if state_mode == "live" and source == "scenario":
        raise MeetingProtocolError("live 组会不能使用 scenario 来源")
    if state_mode == "replay" and source == "live":
        raise MeetingProtocolError("replay 组会不能伪装成 live 来源")
    if source == "live" and kind != "failure" and not any(ref in step_ids for ref in refs):
        raise MeetingProtocolError("live 组会事件必须引用 RunStep")
    if source == "pi" and not refs:
        raise MeetingProtocolError("PI 事件必须引用 PI 操作或 RunStep")
    if source == "pi" and actor_role != "pi":
        raise MeetingProtocolError("PI 来源事件的 actor_role 必须是 pi")
    if source == "pi" and not any(ref in step_ids or ref.startswith("pi:") for ref in refs):
        raise MeetingProtocolError("PI 事件缺少可追溯的操作来源")
    if actor_role == "phd_student" and not (
        kind == "review_gate" and str(getattr(event, "phase", "")) == "review_gate"
    ):
        raise MeetingProtocolError("博士只能在组会前 review_gate，不能在组会汇报")
    if kind == "review_gate":
        if actor_role != "phd_student" or str(getattr(event, "phase", "")) != "review_gate":
            raise MeetingProtocolError("review_gate 事件必须由博士在 review_gate 阶段提交")
        if not any(ref in step_ids for ref in refs):
            raise MeetingProtocolError("review_gate 事件必须引用 RunStep")
    if kind in {"master_report", "agent_report"}:
        if actor_role != "master_student":
            raise MeetingProtocolError("只有硕士 Agent 可以提交 master_report")
        artifact_refs = [ref for ref in refs if ref in artifacts]
        if not artifact_refs or not any(
            _markdown_ref(ref)
            and artifacts[ref].get("artifact_type") == "master_research_markdown"
            and str(artifacts[ref].get("agent_id")) == str(event.actor_id)
            for ref in artifact_refs
        ):
            raise MeetingProtocolError("硕士组会汇报必须引用本人的 Markdown 产物")
    if kind == "candidate_report":
        if actor_role != "master_student":
            raise MeetingProtocolError("只有硕士 Agent 可以提交 candidate_report")
        if not any(ref in step_ids for ref in refs):
            raise MeetingProtocolError("候选汇报必须引用 RunStep")
    if kind == "postdoc_response":
        if not any(
            prior.kind == "postdoc_request"
            and prior.actor_role == "postdoc"
            for prior in previous
        ):
            raise MeetingProtocolError("博士后回答前必须存在专业 request")
    if kind in {"decision", "final_decision"}:
        if any(prior.kind in {"decision", "final_decision"} for prior in previous):
            raise MeetingProtocolError("正式组会只能有一个 PI 最终决策")
        if not all(
            any(
                prior.actor_id == master
                and prior.kind in {"master_report", "agent_report", "candidate_report"}
                for prior in previous
            )
            for master in _masters(run_state)
        ):
            raise MeetingProtocolError("PI 决策前必须完成所有硕士 Markdown 汇报")
    if kind in {"conclusion", "formal_conclusion"} and not any(
        prior.kind in {"decision", "final_decision"} for prior in previous
    ):
        raise MeetingProtocolError("PI 决策前不能产生正式结论")


def validate_meeting_stream(events: Iterable[object], run_state: object) -> None:
    """Validate order, role boundaries and source provenance for a stream."""
    ordered = list(events)
    previous: list[object] = []
    last_sequence = 0
    for event in ordered:
        sequence = int(getattr(event, "sequence", 0))
        if sequence and sequence <= last_sequence:
            raise MeetingProtocolError("组会事件 sequence 必须严格递增")
        last_sequence = sequence or last_sequence
        validate_meeting_event(event, previous=previous, run_state=run_state)
        previous.append(event)

    reports = {
        str(event.actor_id)
        for event in ordered
        if str(event.kind) in {"master_report", "agent_report", "candidate_report"}
    }
    missing = [master for master in _masters(run_state) if master not in reports]
    if missing:
        raise MeetingProtocolError(
            "缺少硕士 Markdown 汇报: " + ", ".join(missing)
        )


def build_formal_meeting_events(run_state: object) -> list[object]:
    """Project eligible RunSteps into the documented formal meeting order."""
    # Import lazily to keep the protocol module independent from service's
    # event model and avoid a circular import.
    from app.meeting.service import MeetingEvent

    mode = str(getattr(run_state, "mode", ""))
    artifacts_by_agent = {
        str(item.get("agent_id")): item
        for item in getattr(run_state, "artifacts", [])
        if item.get("artifact_type") == "master_research_markdown"
    }
    steps = list(getattr(run_state, "steps", []))
    events: list[MeetingEvent] = []
    for step in steps:
        phase = str(getattr(step, "phase", ""))
        kind = str(getattr(step, "kind", ""))
        payload = getattr(step, "payload", {}) or {}
        source_value = payload.get("source")
        if phase == "independent_analysis" and kind == "claim":
            if mode == "live" and source_value != "live":
                continue
            if mode == "replay" and source_value == "live":
                continue
            source = "live" if mode == "live" else "scenario"
            actor = str(getattr(step, "actor", ""))
            refs = [str(getattr(step, "id", ""))]
            artifact = artifacts_by_agent.get(actor)
            if artifact is None:
                raise MeetingProtocolError(f"硕士 {actor} 缺少持久化 Markdown 产物")
            refs.append(str(artifact["artifact_id"]))
            events.append(
                MeetingEvent(
                    id=f"meeting:{run_state.run_id}:report:{step.id}",
                    run_id=run_state.run_id,
                    actor_id=actor,
                    actor_role="master_student",
                    kind="master_report",
                    content=step.content,
                    timestamp=step.timestamp,
                    source_refs=refs,
                    source=source,
                    phase="meeting",
                    sequence=len(events) + 1,
                )
            )
        elif phase == "postdoc_exchange" and kind in {
            "request",
            "in_scope_answer",
            "out_of_scope_refusal",
            "synthesis",
        }:
            source = "live" if mode == "live" else "scenario"
            event_kind = "postdoc_request" if kind == "request" else "postdoc_response"
            events.append(
                MeetingEvent(
                    id=f"meeting:{run_state.run_id}:postdoc:{step.id}",
                    run_id=run_state.run_id,
                    actor_id=str(step.actor),
                    actor_role="postdoc",
                    kind=event_kind,
                    content=step.content,
                    timestamp=step.timestamp,
                    source_refs=[str(step.id)],
                    source=source,
                    phase=phase,
                    sequence=len(events) + 1,
                )
            )
        elif (
            phase == "meeting"
            and kind == "suggested_decision"
            and getattr(run_state, "postdoc_result", {})
        ):
            events.append(
                MeetingEvent(
                    id=f"meeting:{run_state.run_id}:suggestion:{step.id}",
                    run_id=run_state.run_id,
                    actor_id="system",
                    actor_role="system",
                    kind="suggested_decision",
                    content=step.content,
                    timestamp=step.timestamp,
                    source_refs=[str(step.id), *[str(ref) for ref in payload.get("source_refs", [])]],
                    source="live" if mode == "live" else "scenario",
                    phase=phase,
                    sequence=len(events) + 1,
                )
            )
        elif phase == "meeting" and kind in {"decision", "final_decision"}:
            events.append(
                MeetingEvent(
                    id=f"meeting:{run_state.run_id}:decision:{step.id}",
                    run_id=run_state.run_id,
                    actor_id="PI",
                    actor_role="pi",
                    kind="decision",
                    content=step.content,
                    timestamp=step.timestamp,
                    source_refs=[str(step.id)],
                    source="pi",
                    phase=phase,
                    sequence=len(events) + 1,
                )
            )
    if events:
        validate_meeting_stream(events, run_state)
    return events


def build_task_scoped_meeting_events(run_state: object) -> list[object]:
    """Project real-task candidate materials without promoting them to facts.

    Task-scoped live Runs stop at ``awaiting_review``. Their materials do not
    have the Scenario path's Markdown artifacts, so they use candidate report
    events sourced from the corresponding RunSteps. The PhD review remains a
    pre-meeting event and the Postdoc suggestion remains pending; this helper
    never creates a PI decision or formal conclusion.
    """
    if str(getattr(run_state, "mode", "")) != "live":
        return []

    # Import lazily to keep protocol validation independent from service DTOs.
    from app.meeting.service import MeetingEvent

    step_ids = {str(getattr(step, "id", "")) for step in getattr(run_state, "steps", [])}
    events: list[MeetingEvent] = []

    def append_event(
        *,
        step: object,
        actor_role: str,
        kind: str,
        phase: str,
        source_refs: list[str] | None = None,
    ) -> None:
        step_id = str(getattr(step, "id", ""))
        refs = [step_id, *(source_refs or [])]
        refs = list(dict.fromkeys(ref for ref in refs if ref))
        events.append(
            MeetingEvent(
                id=f"meeting:{run_state.run_id}:task:{step_id}",
                run_id=run_state.run_id,
                actor_id=str(getattr(step, "actor", "")),
                actor_role=actor_role,
                kind=kind,
                content=str(getattr(step, "content", "")),
                timestamp=float(getattr(step, "timestamp", 0.0)),
                source_refs=refs,
                source="live",
                phase=phase,
                sequence=len(events) + 1,
            )
        )

    for step in getattr(run_state, "steps", []):
        phase = str(getattr(step, "phase", ""))
        kind = str(getattr(step, "kind", ""))
        payload = getattr(step, "payload", {}) or {}
        if payload.get("source") != "live":
            continue
        if phase == "independent_analysis" and kind == "candidate":
            append_event(
                step=step,
                actor_role="master_student",
                kind="candidate_report",
                phase=phase,
                source_refs=[
                    str(ref)
                    for ref in payload.get("source_refs", [])
                    if isinstance(ref, str)
                ],
            )
        elif phase == "review_gate" and kind == "review_opinion":
            append_event(step=step, actor_role="phd_student", kind="review_gate", phase=phase)
        elif phase == "postdoc_exchange" and kind == "request":
            append_event(step=step, actor_role="postdoc", kind="postdoc_request", phase=phase)
        elif phase == "postdoc_exchange" and kind in {
            "in_scope_answer",
            "out_of_scope_refusal",
            "synthesis",
        }:
            append_event(step=step, actor_role="postdoc", kind="postdoc_response", phase=phase)
        elif kind == "suggested_decision" and phase in {"postdoc_exchange", "meeting"}:
            append_event(
                step=step,
                actor_role="system",
                kind="suggested_decision",
                phase=phase,
                source_refs=[
                    str(ref)
                    for ref in payload.get("source_refs", [])
                    if isinstance(ref, str) and str(ref) in step_ids
                ],
            )

    if events:
        validate_meeting_stream(events, run_state)
    return events
