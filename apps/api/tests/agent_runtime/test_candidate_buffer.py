"""Candidate Streaming Buffer 测试（tasks.md Task 21）。"""
import pytest

from app.agent_runtime.candidate_buffer import (
    CandidateEventNotFoundError,
    append_event,
    list_events,
    mark_rejected,
    mark_validated,
    reset_buffer,
)
from app.agent_runtime.schemas import CandidateStreamEvent


@pytest.fixture(autouse=True)
def _reset():
    reset_buffer()
    yield
    reset_buffer()


def _event(
    event_id: str = "evt-1",
    run_id: str = "run-1",
    status: str = "streaming",
    delta: str = "文本",
) -> CandidateStreamEvent:
    return CandidateStreamEvent(
        id=event_id,
        run_id=run_id,
        agent_id="agent-ms-1",
        content_delta=delta,
        status=status,
    )


def test_append_event_streaming() -> None:
    event = append_event(_event(status="streaming"))
    assert event.status == "streaming"
    assert list_events("run-1") == [event]


def test_append_event_completed() -> None:
    event = append_event(_event(status="completed"))
    assert event.status == "completed"


@pytest.mark.parametrize("bad_status", ["validated", "rejected", "pending"])
def test_append_rejects_non_initial_status(bad_status: str) -> None:
    with pytest.raises(ValueError):
        append_event(_event(status=bad_status))  # type: ignore[arg-type]


def test_list_events_in_append_order() -> None:
    first = append_event(_event("e1", delta="a"))
    second = append_event(_event("e2", delta="b"))
    assert [e.id for e in list_events("run-1")] == ["e1", "e2"]
    assert first.content_delta == "a" and second.content_delta == "b"


def test_list_events_isolated_per_run() -> None:
    append_event(_event("e1", run_id="run-1"))
    append_event(_event("e2", run_id="run-2"))
    assert [e.id for e in list_events("run-1")] == ["e1"]
    assert [e.id for e in list_events("run-2")] == ["e2"]


def test_mark_validated_updates_status() -> None:
    append_event(_event("e1"))
    updated = mark_validated("e1")
    assert updated.status == "validated"
    assert [e.status for e in list_events("run-1")] == ["validated"]


def test_mark_rejected_updates_status() -> None:
    append_event(_event("e1"))
    updated = mark_rejected("e1")
    assert updated.status == "rejected"
    assert [e.status for e in list_events("run-1")] == ["rejected"]


def test_only_explicit_mark_changes_status() -> None:
    append_event(_event("e1"))
    assert [e.status for e in list_events("run-1")] == ["streaming"]
    append_event(_event("e2", status="completed"))
    assert [e.status for e in list_events("run-1")] == ["streaming", "completed"]


def test_mark_unknown_event_raises() -> None:
    with pytest.raises(CandidateEventNotFoundError):
        mark_validated("nope")
    with pytest.raises(CandidateEventNotFoundError):
        mark_rejected("nope")


def test_mark_does_not_create_event() -> None:
    with pytest.raises(CandidateEventNotFoundError):
        mark_validated("ghost")
    assert list_events("run-1") == []


def test_reset_buffer_clears_all() -> None:
    append_event(_event("e1", run_id="run-1"))
    append_event(_event("e2", run_id="run-2"))
    reset_buffer()
    assert list_events("run-1") == []
    assert list_events("run-2") == []


def test_buffer_does_not_write_memory_timeline() -> None:
    """buffer 不写 MemoryTimeline（导入面检查）。"""
    import inspect

    from app.agent_runtime import candidate_buffer as module

    source = inspect.getsource(module)
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    for forbidden in ("memory", "MemoryTimeline", "orchestration", "llm", "httpx"):
        assert not any(forbidden in line for line in import_lines), forbidden
