"""正式组会事件流服务。

RunStep 是 Run 的事实来源，MeetingEvent 是面向组会记录的持久化投影。
该模块不调用 Agent Runtime 或 HTTP，只编排既有 RunStore、Repository 和
状态机能力。
"""

from __future__ import annotations

import copy
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from threading import Lock, RLock
from typing import Iterator, Literal

from pydantic import BaseModel, Field

from app.orchestration.engine import apply_decision
from app.orchestration.run_store import RunState, RunStore
from app.scenario.loader import load_scenario
from app.storage.repositories import MeetingRepository
from app.meeting.protocol import (
    MeetingProtocolError,
    build_formal_meeting_events,
    build_task_scoped_meeting_events,
    validate_meeting_event,
)


class MeetingEvent(BaseModel):
    """正式组会事件的最小可恢复字段。"""

    id: str
    run_id: str
    actor_id: str
    actor_role: str
    kind: str
    content: str
    timestamp: float
    source_refs: list[str] = Field(default_factory=list)
    source: Literal["live", "scenario", "pi"] = "live"
    phase: str = "meeting"
    sequence: int = 0


class MeetingService:
    """Append and recover formal meeting events for Run instances."""

    def __init__(
        self,
        run_store: RunStore,
        repository: MeetingRepository,
        *,
        scenario_loader: Callable[[str], object] = load_scenario,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._run_store = run_store
        self._repository = repository
        self._scenario_loader = scenario_loader
        self._clock = clock
        self._locks: dict[str, RLock] = {}
        self._locks_guard = Lock()

    def list_meeting_events(self, run_id: str) -> list[MeetingEvent]:
        """Read the complete ordered event stream for one Run."""
        state = self._run_store.get(run_id)
        if state is not None:
            with self.transaction(run_id):
                if self._is_task_scoped(state):
                    self.sync_task_materials(state)
                else:
                    self.sync_live_reports(state)
                if state.mode == "live" and state.status == "failed" and state.error:
                    failure_refs = [
                        step.id
                        for step in state.steps
                        if step.kind == "invocation"
                        and step.payload.get("status") == "error"
                    ]
                    self.append_failure(
                        state,
                        state.error,
                        source_refs=failure_refs,
                    )
        return [self._from_record(record) for record in self._repository.list_events(run_id)]

    def append_pi_message(self, run_id: str, content: str) -> MeetingEvent:
        """Persist one PI interruption without changing formal research state."""
        with self.transaction(run_id):
            state = self._require_run(run_id)
            if state.phase != "meeting":
                raise ValueError("只能在 meeting 阶段发送 PI 插话")
            normalized = content.strip() if isinstance(content, str) else ""
            if not normalized:
                raise ValueError("PI 插话内容不能为空")
            return self._append(
                MeetingEvent(
                    id=f"meeting-{uuid.uuid4().hex[:12]}",
                    run_id=run_id,
                    actor_id="PI",
                    actor_role="pi",
                    kind="message",
                    content=normalized,
                    timestamp=self._clock(),
                    source_refs=[],
                    source="pi",
                    phase=state.phase,
                )
            )

    def apply_pi_decision(self, run_id: str, option: str, reason: str) -> RunState:
        """Apply an existing PI decision transition and persist its event."""
        with self.transaction(run_id):
            state = self._require_run(run_id)
            if self._is_task_scoped(state):
                self.sync_task_materials(state)
            else:
                self.sync_live_reports(state)
            if state.status != "awaiting_decision" or state.phase != "meeting":
                raise ValueError("只能在 awaiting_decision 的 meeting 阶段进行 PI 裁决")
            original = (
                state.status,
                state.phase,
                state.cycle,
                state.error,
                copy.deepcopy(state.steps),
                copy.deepcopy(state.memory),
            )
            try:
                previous_step_ids = {step.id for step in state.steps}
                scenario = self._scenario_loader("foam_concrete_case")
                apply_decision(scenario, state, option, reason)
                decision_step = next(
                    step
                    for step in state.steps
                    if step.id not in previous_step_ids and step.kind == "decision"
                )
                self._append(
                    MeetingEvent(
                        id=f"meeting:{run_id}:decision:{decision_step.id}",
                        run_id=run_id,
                        actor_id="PI",
                        actor_role="pi",
                        kind="decision",
                        content=decision_step.content,
                        timestamp=self._clock(),
                        source_refs=[decision_step.id],
                        source="pi",
                        phase="meeting",
                    )
                )
            except Exception:
                state.status, state.phase, state.cycle, state.error = original[:4]
                state.steps = original[4]
                state.memory = original[5]
                raise
            return state

    def sync_live_reports(self, state: RunState) -> list[MeetingEvent]:
        """Project successful live claim steps into the formal meeting stream.

        Stable IDs make this safe to call after a Run is resumed or after a
        client repeats a poll. Replay and failed steps are intentionally not
        eligible for this projection.
        """
        try:
            candidates = build_formal_meeting_events(state)
        except MeetingProtocolError:
            # A failed live run may have only a prefix of the master reports;
            # preserve that prefix and its failure event without fabricating
            # the missing reports. Awaiting-decision runs remain strict.
            if state.status != "failed":
                raise
            candidates = self._partial_formal_events(state)
        existing = {event.id for event in self._read_events(state.run_id)}
        return [self._append(event) for event in candidates if event.id not in existing]

    @staticmethod
    def _is_task_scoped(state: RunState) -> bool:
        return (
            state.mode == "live"
            and state.task_context.get("completion_mode") == "candidate_review"
        )

    def sync_task_materials(self, state: RunState) -> list[MeetingEvent]:
        """Project candidate/review/Postdoc materials without creating PI facts."""
        try:
            candidates = build_task_scoped_meeting_events(state)
        except MeetingProtocolError:
            if state.status not in {"failed", "queued", "running"}:
                raise
            completed_master_ids = {
                step.actor
                for step in state.steps
                if step.phase == "independent_analysis"
                and step.kind == "candidate"
                and step.payload.get("source") == "live"
            }
            partial_state = copy.copy(state)
            partial_state.agent_specs = [
                spec for spec in state.agent_specs
                if str(spec.get("agent_id", "")) in completed_master_ids
            ]
            candidates = build_task_scoped_meeting_events(partial_state)
        existing = {event.id for event in self._read_events(state.run_id)}
        return [self._append(event) for event in candidates if event.id not in existing]

    @contextmanager
    def transaction(self, run_id: str | None = None) -> Iterator[None]:
        """Run state and meeting projection writes in one guarded transaction."""
        lock = self._lock_for(run_id) if run_id else None
        if lock is None:
            with self._repository.store.transaction():
                yield
            return
        with lock:
            with self._repository.store.transaction():
                yield

    def append_failure(
        self,
        state: RunState,
        error: str,
        *,
        source_refs: list[str] | None = None,
    ) -> MeetingEvent:
        """Persist a stable failure event for a failed live Run."""
        normalized = error.strip() if isinstance(error, str) else "运行失败"
        return self._append(
            MeetingEvent(
                id=f"meeting:{state.run_id}:failure",
                run_id=state.run_id,
                actor_id="system",
                actor_role="system",
                kind="failure",
                content=normalized or "运行失败",
                timestamp=self._clock(),
                source_refs=list(source_refs or []),
                source="live",
                phase="failed",
            )
        )

    def _read_events(self, run_id: str) -> list[MeetingEvent]:
        return [self._from_record(record) for record in self._repository.list_events(run_id)]

    @staticmethod
    def _partial_formal_events(state: RunState) -> list[MeetingEvent]:
        """Build only the eligible prefix when a live run failed early."""
        from app.meeting.protocol import build_formal_meeting_events

        original_status = state.status
        try:
            state.status = "awaiting_decision"
            return build_formal_meeting_events(state)
        except MeetingProtocolError:
            # The protocol builder validates the complete stream. For a failed
            # prefix, retain only reports with a real artifact and RunStep.
            reports: list[MeetingEvent] = []
            artifacts = {
                item.get("agent_id"): item for item in state.artifacts
            }
            sequence = 0
            for step in state.steps:
                if (
                    step.phase != "independent_analysis"
                    or step.kind != "claim"
                    or step.payload.get("source") != "live"
                ):
                    continue
                artifact = artifacts.get(step.actor)
                if artifact is None:
                    continue
                sequence += 1
                reports.append(
                    MeetingEvent(
                        id=f"meeting:{state.run_id}:report:{step.id}",
                        run_id=state.run_id,
                        actor_id=step.actor,
                        actor_role="master_student",
                        kind="master_report",
                        content=step.content,
                        timestamp=step.timestamp,
                        source_refs=[step.id, artifact["artifact_id"]],
                        source="live",
                        phase="meeting",
                        sequence=sequence,
                    )
                )
            return reports
        finally:
            state.status = original_status

    def _require_run(self, run_id: str) -> RunState:
        state = self._run_store.get(run_id)
        if state is None:
            raise ValueError(f"Run 不存在: {run_id}")
        return state

    def _lock_for(self, run_id: str) -> RLock:
        with self._locks_guard:
            return self._locks.setdefault(run_id, RLock())

    def _append(self, event: MeetingEvent) -> MeetingEvent:
        state = self._run_store.get(event.run_id)
        if event.sequence <= 0:
            event.sequence = len(self._repository.list_events(event.run_id)) + 1
        if event.source == "pi" and not event.source_refs:
            event.source_refs = [f"pi:{event.id}"]
        if state is not None:
            previous = self._read_events(event.run_id)
            validate_meeting_event(event, previous=previous, run_state=state)
        self._repository.append_event(
            {
                "event_id": event.id,
                "run_id": event.run_id,
                "actor_id": event.actor_id,
                "actor_role": event.actor_role,
                "kind": event.kind,
                "content": event.content,
                "timestamp": event.timestamp,
                "source_refs": list(event.source_refs),
                "source": event.source,
                "phase": event.phase,
                "sequence": event.sequence,
            }
        )
        return event

    @staticmethod
    def _from_record(record: dict) -> MeetingEvent:
        return MeetingEvent(
            id=record["event_id"],
            run_id=record["run_id"],
            actor_id=record["actor_id"],
            actor_role=record["actor_role"],
            kind=record["kind"],
            content=record["content"],
            timestamp=record["timestamp"],
            source_refs=list(record.get("source_refs", [])),
            source=record.get("source", "live"),
            phase=record.get("phase", "meeting"),
            sequence=int(record.get("sequence", 0)),
        )
