"""Run state storage with optional SQLite snapshot persistence."""
from __future__ import annotations

import json
import time
import uuid
import copy
from dataclasses import dataclass, field
from typing import Callable, Literal

from app.memory.timeline import MemoryTimeline
from app.tools.audit import AuditRecorder
from app.tools.audit_repository import ToolAuditRepository
from app.tools.schemas import ToolCallRecord
from app.agent_runtime.schemas import RuntimeSessionRef
from app.storage.repositories import ArtifactRepository, RunRepository, RuntimeEventRepository, RuntimeSessionRepository
from app.storage.sqlite_store import SQLiteStore


@dataclass(frozen=True)
class RunStep:
    id: str
    phase: str
    kind: str
    actor: str
    content: str
    payload: dict
    timestamp: float


@dataclass
class RunState:
    run_id: str
    group_chat_id: str
    mode: Literal["replay", "live"]
    status: Literal[
        "queued",
        "running",
        "awaiting_review",
        "awaiting_decision",
        "completed",
        "cancelled",
        "terminated",
        "cycle_exhausted",
        "failed",
    ]
    phase: str
    cycle: int
    task_id: str = ""
    candidate_ids: list[str] = field(default_factory=list)
    agent_specs: list[dict] = field(default_factory=list)
    review_agent_spec: dict = field(default_factory=dict)
    postdoc_agent_spec: dict = field(default_factory=dict)
    runtime_name: str = ""
    task_context: dict = field(default_factory=dict)
    artifacts: list[dict] = field(default_factory=list)
    error: str = ""
    review_result: dict = field(default_factory=dict)
    postdoc_result: dict = field(default_factory=dict)
    pi_suggestion: dict = field(default_factory=dict)
    agent_attempts: dict[str, int] = field(default_factory=dict)
    current_agent_id: str = ""
    current_phase: str = ""
    current_invocation_id: str = ""
    steps: list = field(default_factory=list)
    memory: MemoryTimeline = field(default_factory=MemoryTimeline)
    tool_audit_records: list[ToolCallRecord] = field(default_factory=list)
    session_refs: dict[str, RuntimeSessionRef] = field(default_factory=dict)
    runtime_cursor: int = 0
    control_state: str = "running"
    runtime_events: list[dict] = field(default_factory=list)
    tool_audit_recorder: AuditRecorder = field(init=False, repr=False)
    _persist_callback: Callable[["RunState"], None] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _artifact_callback: Callable[["RunState", dict], None] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self.tool_audit_recorder = AuditRecorder(sink=self.tool_audit_records.append)

    def configure_audit_persistence(self, repository: ToolAuditRepository | None) -> None:
        def sink(record: ToolCallRecord) -> None:
            self.tool_audit_records.append(record.model_copy(deep=True))
            if repository is not None:
                repository.append(record)

        self.tool_audit_recorder = AuditRecorder(sink=sink)

    def persist(self) -> None:
        """Persist this state when it belongs to a durable RunStore."""
        if self._persist_callback is not None:
            self._persist_callback(self)

    def persist_artifact(self, artifact: dict) -> None:
        if self._artifact_callback is not None:
            self._artifact_callback(self, artifact)
        elif not any(item.get("artifact_id") == artifact.get("artifact_id") for item in self.artifacts):
            self.artifacts.append(copy.deepcopy(artifact))


class RunStore:
    def __init__(self, store: SQLiteStore | None = None) -> None:
        self._runs: dict[str, RunState] = {}
        self._persistence_store = store
        self._run_repository = RunRepository(store) if store is not None else None
        self._artifact_repository = ArtifactRepository(store) if store is not None else None
        self._runtime_session_repository = RuntimeSessionRepository(store) if store is not None else None
        self._runtime_event_repository = RuntimeEventRepository(store) if store is not None else None
        self._tool_audit_repository = ToolAuditRepository(store) if store is not None else None

    def configure_persistence(self, store: SQLiteStore | None) -> None:
        """Attach or detach the durable store without replacing this object."""
        self._persistence_store = store
        self._run_repository = RunRepository(store) if store is not None else None
        self._artifact_repository = ArtifactRepository(store) if store is not None else None
        self._runtime_session_repository = RuntimeSessionRepository(store) if store is not None else None
        self._runtime_event_repository = RuntimeEventRepository(store) if store is not None else None
        self._tool_audit_repository = ToolAuditRepository(store) if store is not None else None

    def create(
        self,
        group_chat_id: str,
        mode: Literal["replay", "live"],
        *,
        task_id: str = "",
        agent_specs: list[dict] | None = None,
        review_agent_spec: dict | None = None,
        postdoc_agent_spec: dict | None = None,
        runtime_name: str = "",
        task_context: dict | None = None,
    ) -> RunState:
        resolved_task_id = str(task_id or (task_context or {}).get("task_id", ""))
        resolved_task_context = copy.deepcopy(task_context or {})
        if resolved_task_id:
            resolved_task_context.setdefault("task_id", resolved_task_id)
        state = RunState(
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            group_chat_id=group_chat_id,
            mode=mode,
            status="running",
            phase="independent_analysis",
            cycle=1,
            task_id=resolved_task_id,
            agent_specs=[copy.deepcopy(spec) for spec in (agent_specs or [])],
            review_agent_spec=copy.deepcopy(review_agent_spec or {}),
            postdoc_agent_spec=copy.deepcopy(postdoc_agent_spec or {}),
            runtime_name=runtime_name,
            task_context=resolved_task_context,
        )
        state._persist_callback = self.save
        state._artifact_callback = self.save_artifact
        state.configure_audit_persistence(self._tool_audit_repository)
        self._runs[state.run_id] = state
        self.save(state)
        return state

    def get(self, run_id: str) -> RunState | None:
        state = self._runs.get(run_id)
        if state is not None or self._run_repository is None:
            return state
        record = self._run_repository.get_snapshot(run_id)
        if record is None:
            return None
        state = _restore_state(record["snapshot"])
        state._persist_callback = self.save
        state._artifact_callback = self.save_artifact
        state.configure_audit_persistence(self._tool_audit_repository)
        self._runs[run_id] = state
        return state

    def get_latest_for_task(self, group_chat_id: str, task_id: str) -> RunState | None:
        in_memory = [
            state
            for state in self._runs.values()
            if state.group_chat_id == group_chat_id and state.task_id == task_id
        ]
        if in_memory:
            return in_memory[-1]
        if self._run_repository is None:
            return None
        snapshot = self._run_repository.get_latest_for_task(group_chat_id, task_id)
        return None if snapshot is None else self.get(snapshot["run_id"])

    def resume_run(self, run_id: str) -> RunState | None:
        """Hydrate a persisted Run and its runtime log without creating a Run."""
        state = self.get(run_id)
        if state is None:
            return None
        if self._runtime_session_repository is not None:
            session_refs = dict(state.session_refs)
            for record in self._runtime_session_repository.list_for_run(run_id):
                recovered = RuntimeSessionRef.model_validate(_decode_session_scope(record))
                previous = next(
                    (
                        existing
                        for existing in session_refs.values()
                        if existing.session_id == recovered.session_id
                    ),
                    None,
                )
                if previous is not None:
                    recovered = previous.model_copy(
                        update={"last_cursor": max(previous.last_cursor, recovered.last_cursor)}
                    )
                key = _session_ref_key(recovered)
                previous = session_refs.get(key)
                if previous is not None:
                    recovered = recovered.model_copy(
                        update={"last_cursor": max(previous.last_cursor, recovered.last_cursor)}
                    )
                session_refs[key] = recovered
            state.session_refs = session_refs
        if self._runtime_event_repository is not None:
            state.runtime_events = self._runtime_event_repository.list_for_run(run_id)
            state.runtime_cursor = max(
                state.runtime_cursor,
                self._runtime_event_repository.get_cursor(run_id),
                max((int(event["cursor"]) for event in state.runtime_events), default=0),
            )
        return state

    def save(self, state: RunState) -> None:
        """Save the raw state needed to reconstruct a RunState."""
        if self._run_repository is None:
            return
        now = time.time()
        self._run_repository.save_snapshot(
            {
                "run_id": state.run_id,
                "group_chat_id": state.group_chat_id,
                "task_id": state.task_id,
                "status": state.status,
                "mode": state.mode,
                "phase": state.phase,
                "cycle": state.cycle,
                "snapshot": _serialize_state(state),
                "created_at": now,
                "updated_at": now,
            }
        )

    def save_artifact(self, state: RunState, artifact: dict) -> None:
        item = copy.deepcopy(artifact)
        if self._artifact_repository is not None:
            self._artifact_repository.save(item)
        state.artifacts = [
            item if existing.get("artifact_id") == item.get("artifact_id") else existing
            for existing in state.artifacts
        ]
        if not any(existing.get("artifact_id") == item.get("artifact_id") for existing in state.artifacts):
            state.artifacts.append(item)
        self.save(state)

    def reset(self) -> None:
        self._runs.clear()
        if self._run_repository is not None:
            self._run_repository.delete_all()
        if self._artifact_repository is not None:
            self._artifact_repository.delete_all()
        if self._runtime_session_repository is not None:
            self._runtime_session_repository.delete_all()
        if self._runtime_event_repository is not None:
            self._runtime_event_repository.delete_all()

    def delete_for_group(self, group_chat_id: str) -> None:
        """Drop cached snapshots for a deleted group after DB cleanup."""
        self._runs = {
            run_id: state
            for run_id, state in self._runs.items()
            if state.group_chat_id != group_chat_id
        }

    def get_audit_recorder(self, run_id: str) -> AuditRecorder:
        state = self.get(run_id)
        if state is None:
            raise KeyError(run_id)
        return state.tool_audit_recorder

    def list_tool_audit(self, run_id: str) -> list[ToolCallRecord]:
        if self._tool_audit_repository is not None:
            return self._tool_audit_repository.list_for_run(run_id)
        state = self.get(run_id)
        if state is None:
            return []
        return [record.model_copy(deep=True) for record in state.tool_audit_records]

    def list_successful_source_refs(self, run_id: str, agent_id: str | None = None) -> set[str]:
        if self._tool_audit_repository is not None:
            return self._tool_audit_repository.list_successful_source_refs(run_id, agent_id)
        return {
            ref
            for record in self.list_tool_audit(run_id)
            if record.status == "success" and (agent_id is None or record.agent_id == agent_id)
            for ref in record.source_refs
        }

    def save_runtime_session(
        self, ref: RuntimeSessionRef, *, session_scope: str = "", session_file: str | None = None
    ) -> None:
        if self._runtime_session_repository is None:
            return
        now = time.time()
        self._runtime_session_repository.upsert({
            **ref.model_dump(mode="json"), "session_scope": _encode_session_scope(session_scope, ref),
            "session_file": session_file, "created_at": now, "updated_at": now,
        })

    def prepare_runtime_event(self, state: RunState, event: dict) -> dict:
        """Copy an event and assign the next Run-global SSE recovery cursor."""
        event_id = event.get("event_id")
        for existing in state.runtime_events:
            if existing.get("event_id") == event_id:
                return copy.deepcopy(existing)
        prepared = copy.deepcopy(event)
        prepared["cursor"] = state.runtime_cursor + 1
        return prepared

    def ensure_run_started_event(self, state: RunState, *, agent_id: str) -> dict:
        """Persist the server-owned start fact before an agent runtime begins."""
        existing = next(
            (event for event in state.runtime_events if event.get("type") == "run_started"),
            None,
        )
        if existing is not None:
            return copy.deepcopy(existing)
        if not agent_id.strip():
            raise ValueError("run_started event requires an agent_id")
        task_context = state.task_context or {}
        event = self.prepare_runtime_event(
            state,
            {
                "event_id": f"run-started:{state.run_id}",
                "cursor": 0,
                "session_id": f"server:{state.run_id}",
                "invocation_id": f"run-started:{state.run_id}",
                "run_id": state.run_id,
                "group_chat_id": state.group_chat_id,
                "agent_id": agent_id,
                "phase": state.phase or "independent_analysis",
                "type": "run_started",
                "payload": {"status": "running"},
                "data_space": str(task_context.get("data_space", "synthetic")),
                "task_id": state.task_id,
                "document_scope": list(task_context.get(
                    "allowed_document_ids", task_context.get("document_ids", [])
                )),
                "timestamp": time.time(),
            },
        )
        from app.agent_runtime.event_bridge import project_runtime_event

        project_runtime_event(state, event)
        self.save_runtime_event(state, event)
        return copy.deepcopy(event)

    def save_runtime_event(self, state: RunState, event: dict) -> None:
        if event.get("run_id") != state.run_id or event.get("group_chat_id") != state.group_chat_id:
            raise ValueError("runtime event identity mismatch")
        session_cursor = int(event["cursor"])
        existing_index = next(
            (
                index
                for index, item in enumerate(state.runtime_events)
                if item.get("event_id") == event.get("event_id")
            ),
            None,
        )
        existing = (
            state.runtime_events[existing_index]
            if existing_index is not None
            else None
        )
        previous_run_cursor = (
            self._runtime_event_repository.get_cursor(state.run_id)
            if self._runtime_event_repository is not None
            else max(
                (
                    int(item["cursor"])
                    for item in state.runtime_events
                    if item.get("event_id") != event.get("event_id")
                ),
                default=0,
            )
        )
        if (
            existing is not None
            and int(existing["cursor"]) == session_cursor
            and (
                self._runtime_event_repository is None
                or previous_run_cursor >= int(existing["cursor"])
            )
        ):
            state.runtime_cursor = max(state.runtime_cursor, int(existing["cursor"]))
            return
        run_cursor = max(previous_run_cursor + 1, session_cursor)
        stored_event = {**event, "cursor": run_cursor}
        appended = True
        if self._runtime_event_repository is not None:
            appended = self._runtime_event_repository.append_once(stored_event)
        if existing_index is not None:
            state.runtime_events[existing_index] = copy.deepcopy(stored_event)
        elif appended and not any(
            item.get("event_id") == stored_event.get("event_id")
            or (
                item.get("session_id") == stored_event.get("session_id")
                and item.get("cursor") == stored_event.get("cursor")
            )
            for item in state.runtime_events
        ):
            state.runtime_events.append(copy.deepcopy(stored_event))
        state.runtime_cursor = max(state.runtime_cursor, run_cursor)
        state.persist()

    def list_runtime_events(self, run_id: str, *, after: int = 0) -> list[dict]:
        if self._runtime_event_repository is not None:
            return self._runtime_event_repository.list_for_run(run_id, after=after)
        state = self.get(run_id)
        if state is None:
            return []
        return [copy.deepcopy(event) for event in state.runtime_events if int(event["cursor"]) > after]


def _serialize_state(state: RunState) -> dict:
    """Serialize only fields that are required for a RunState recovery."""
    return {
        "run_id": state.run_id,
        "group_chat_id": state.group_chat_id,
        "mode": state.mode,
        "status": state.status,
        "phase": state.phase,
        "cycle": state.cycle,
        "task_id": state.task_id,
        "candidate_ids": list(state.candidate_ids),
        "agent_specs": [copy.deepcopy(spec) for spec in state.agent_specs],
        "review_agent_spec": copy.deepcopy(state.review_agent_spec),
        "postdoc_agent_spec": copy.deepcopy(state.postdoc_agent_spec),
        "runtime_name": state.runtime_name,
        "task_context": copy.deepcopy(state.task_context),
        "artifacts": [copy.deepcopy(item) for item in state.artifacts],
        "error": state.error,
        "review_result": copy.deepcopy(state.review_result),
        "postdoc_result": copy.deepcopy(state.postdoc_result),
        "pi_suggestion": copy.deepcopy(state.pi_suggestion),
        "agent_attempts": dict(state.agent_attempts),
        "current_agent_id": state.current_agent_id,
        "current_phase": state.current_phase,
        "current_invocation_id": state.current_invocation_id,
        "steps": [
            {
                "id": step.id,
                "phase": step.phase,
                "kind": step.kind,
                "actor": step.actor,
                "content": step.content,
                "payload": step.payload,
                "timestamp": step.timestamp,
            }
            for step in state.steps
        ],
        "memory": [
            {
                "id": entry.id,
                "kind": entry.kind,
                "payload": entry.payload,
                "version": entry.version,
                "supersedes": entry.supersedes,
                "created_at": entry.created_at,
                "object_key": entry.object_key,
                "data_space": entry.data_space,
            }
            for entry in state.memory.entries()
        ],
        "tool_audit_records": [
            record.model_dump(mode="json") for record in state.tool_audit_records
        ],
        "session_refs": {
            agent_id: ref.model_dump(mode="json") for agent_id, ref in state.session_refs.items()
        },
        "runtime_cursor": state.runtime_cursor,
        "control_state": state.control_state,
        "runtime_events": [copy.deepcopy(event) for event in state.runtime_events],
    }


def _restore_state(snapshot: dict) -> RunState:
    """Build a new state object from a validated raw snapshot."""
    from app.memory.timeline import MemoryEntry

    timeline = MemoryTimeline()
    timeline._entries = [
        MemoryEntry(
            id=entry["id"],
            kind=entry["kind"],
            payload=entry["payload"],
            version=entry["version"],
            supersedes=entry.get("supersedes"),
            created_at=entry["created_at"],
            object_key=entry.get("object_key"),
            data_space=entry.get("data_space", "synthetic"),
        )
        for entry in snapshot.get("memory", [])
    ]
    return RunState(
        run_id=snapshot["run_id"],
        group_chat_id=snapshot["group_chat_id"],
        mode=snapshot["mode"],
        status=snapshot["status"],
        phase=snapshot["phase"],
        cycle=snapshot["cycle"],
        task_id=str(snapshot.get("task_id", snapshot.get("task_context", {}).get("task_id", ""))),
        candidate_ids=[str(item) for item in snapshot.get("candidate_ids", [])],
        agent_specs=[copy.deepcopy(spec) for spec in snapshot.get("agent_specs", [])],
        review_agent_spec=copy.deepcopy(snapshot.get("review_agent_spec", {})),
        postdoc_agent_spec=copy.deepcopy(snapshot.get("postdoc_agent_spec", {})),
        runtime_name=snapshot.get("runtime_name", ""),
        task_context=copy.deepcopy(snapshot.get("task_context", {})),
        artifacts=[copy.deepcopy(item) for item in snapshot.get("artifacts", [])],
        error=snapshot.get("error", ""),
        review_result=copy.deepcopy(snapshot.get("review_result", {})),
        postdoc_result=copy.deepcopy(snapshot.get("postdoc_result", {})),
        pi_suggestion=copy.deepcopy(snapshot.get("pi_suggestion", {})),
        agent_attempts={
            str(agent_id): int(attempt)
            for agent_id, attempt in snapshot.get("agent_attempts", {}).items()
        },
        current_agent_id=str(snapshot.get("current_agent_id", "")),
        current_phase=str(snapshot.get("current_phase", "")),
        current_invocation_id=str(snapshot.get("current_invocation_id", "")),
        steps=[RunStep(**step) for step in snapshot.get("steps", [])],
        memory=timeline,
        tool_audit_records=[
            ToolCallRecord.model_validate(record)
            for record in snapshot.get("tool_audit_records", [])
        ],
        session_refs={
            agent_id: RuntimeSessionRef.model_validate(ref)
            for agent_id, ref in snapshot.get("session_refs", {}).items()
        },
        runtime_cursor=int(snapshot.get("runtime_cursor", 0)),
        control_state=str(snapshot.get("control_state", "running")),
        runtime_events=[copy.deepcopy(event) for event in snapshot.get("runtime_events", [])],
    )


def _session_ref_key(ref: RuntimeSessionRef) -> str:
    if ref.attempt > 1:
        return f"{ref.agent_id}:attempt-{ref.attempt}"
    return ref.agent_id


_SESSION_SCOPE_MARKER = "|forummind-session-meta="


def _encode_session_scope(scope: str, ref: RuntimeSessionRef) -> str:
    """Carry retry identity through the pre-P2 runtime_sessions schema."""
    base = str(scope or "").split(_SESSION_SCOPE_MARKER, 1)[0]
    metadata = json.dumps(
        {
            "invocation_id": ref.invocation_id,
            "attempt": ref.attempt,
            "retry_of": ref.retry_of,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{base}{_SESSION_SCOPE_MARKER}{metadata}"


def _decode_session_scope(record: dict) -> dict:
    value = dict(record)
    scope = str(value.get("session_scope", ""))
    if _SESSION_SCOPE_MARKER not in scope:
        return value
    _, raw_metadata = scope.split(_SESSION_SCOPE_MARKER, 1)
    try:
        metadata = json.loads(raw_metadata)
    except (TypeError, ValueError):
        return value
    if not isinstance(metadata, dict):
        return value
    if isinstance(metadata.get("invocation_id"), str):
        value["invocation_id"] = metadata["invocation_id"]
    if isinstance(metadata.get("attempt"), int) and metadata["attempt"] >= 1:
        value["attempt"] = metadata["attempt"]
    if isinstance(metadata.get("retry_of"), str):
        value["retry_of"] = metadata["retry_of"]
    return value
