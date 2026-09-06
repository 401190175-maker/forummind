"""真组会预演上下文快照测试（tasks.md Task 2）。"""

import itertools
from types import SimpleNamespace

import pytest

from app.memory.timeline import MemoryTimeline
import app.memory.timeline as memory_timeline
from app.orchestration.run_store import RunState, RunStep
from app.scenario.loader import load_scenario
from app.meeting_rehearsal.service import build_rehearsal_context


@pytest.fixture(autouse=True)
def _isolate_memory_ids(monkeypatch):
    """Keep this module's fixture IDs independent from other test modules."""
    monkeypatch.setattr(memory_timeline, "_seq", itertools.count(1))


def _group_chat(data_space: str = "synthetic") -> SimpleNamespace:
    return SimpleNamespace(
        group_chat=SimpleNamespace(data_space=data_space),
        topic=SimpleNamespace(
            topic_name="废弃泥浆基泡沫混凝土",
            topic_summary="验证泥浆条件、气泡稳定与孔结构的关系",
        ),
    )


def _run_state() -> RunState:
    state = RunState(
        run_id="run-1",
        group_chat_id="gc-1",
        mode="replay",
        status="awaiting_decision",
        phase="meeting",
        cycle=1,
    )
    state.steps.append(
        RunStep(
            id="step-1",
            phase="review_gate",
            kind="review_opinion",
            actor="agent-phd-1",
            content="样品对应关系缺失",
            payload={"kind": "missing_observation"},
            timestamp=1.0,
        )
    )
    state.memory = MemoryTimeline()
    state.memory.append("ReviewGate", {"items": ["样品对应关系缺失"]})
    return state


def test_context_contains_minimal_run_and_memory_projections() -> None:
    context = build_rehearsal_context(
        _group_chat(), _run_state(), load_scenario("foam_concrete_case")
    )

    assert context.group_chat_id == "gc-1"
    assert context.topic_name == "废弃泥浆基泡沫混凝土"
    assert context.run_id == "run-1"
    assert context.run_phase == "meeting"
    assert context.run_cycle == 1
    assert context.step_summaries[0]["id"] == "step-1"
    assert context.memory_refs == ["mem-1"]
    assert context.data_space.value == "synthetic"


def test_context_is_frozen_and_does_not_hold_mutable_run_objects() -> None:
    run_state = _run_state()
    context = build_rehearsal_context(
        _group_chat(), run_state, load_scenario("foam_concrete_case")
    )
    original_memory_refs = list(context.memory_refs)

    run_state.steps[0].payload["kind"] = "changed after creation"
    run_state.steps.append(
        RunStep(
            id="step-2",
            phase="meeting",
            kind="agenda",
            actor="system",
            content="new step",
            payload={},
            timestamp=2.0,
        )
    )
    run_state.memory.append("ReviewGate", {"items": ["new entry"]})

    assert context.step_summaries[0]["payload"]["kind"] == "missing_observation"
    assert len(context.step_summaries) == 1
    assert context.memory_refs == original_memory_refs


def test_context_without_run_uses_topic_and_scenario() -> None:
    context = build_rehearsal_context(
        _group_chat(), None, load_scenario("foam_concrete_case")
    )

    assert context.run_id is None
    assert context.run_phase is None
    assert context.run_cycle is None
    assert context.scenario_summary == load_scenario("foam_concrete_case").final_state.summary


def test_context_rejects_non_synthetic_group_chat() -> None:
    with pytest.raises(ValueError, match="synthetic"):
        build_rehearsal_context(
            _group_chat("real"), None, load_scenario("foam_concrete_case")
        )
