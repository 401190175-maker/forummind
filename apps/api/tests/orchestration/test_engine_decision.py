"""apply_decision 五裁决分支测试。"""
import pytest

from app.orchestration.engine import apply_decision, run_replay
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario


def _at_meeting():
    store = RunStore()
    state = store.create("gc-1", "replay")
    run_replay(load_scenario("foam_concrete_case"), state)
    return state


def test_invalid_option_raises():
    with pytest.raises(ValueError):
        apply_decision(load_scenario("foam_concrete_case"), _at_meeting(), "maybe", "r")


def test_decision_requires_awaiting_decision_phase():
    store = RunStore()
    state = store.create("gc-1", "replay")
    with pytest.raises(ValueError, match="只能在 awaiting_decision"):
        apply_decision(load_scenario("foam_concrete_case"), state, "approved", "r")


def test_approved_advances_to_experiment():
    state = _at_meeting()
    apply_decision(load_scenario("foam_concrete_case"), state, "approved", "r")
    assert state.status == "completed"
    assert state.phase == "discriminating_experiment"


def test_returned_advances_cycle_and_has_next_meeting():
    state = _at_meeting()
    apply_decision(load_scenario("foam_concrete_case"), state, "returned", "证据不足")
    assert state.cycle == 2
    assert state.status == "awaiting_decision"
    decision_step = [s for s in state.steps if s.kind == "decision"][-1]
    assert decision_step.payload.get("next_meeting") == "第 2 周组会"


def test_deferred_advances_cycle():
    state = _at_meeting()
    apply_decision(load_scenario("foam_concrete_case"), state, "deferred", "r")
    assert state.cycle == 2


def test_terminated():
    state = _at_meeting()
    apply_decision(load_scenario("foam_concrete_case"), state, "terminated", "r")
    assert state.status == "terminated"
    assert state.phase == "terminated"


def test_approved_with_conditions():
    state = _at_meeting()
    apply_decision(load_scenario("foam_concrete_case"), state, "approved_with_conditions", "r")
    assert state.phase == "discriminating_experiment"


def test_research_state_versions_share_object_key_after_returned_then_approved():
    scenario = load_scenario("foam_concrete_case")
    state = _at_meeting()

    apply_decision(scenario, state, "returned", "证据不足")
    apply_decision(scenario, state, "approved", "补齐后批准")

    research_states = [e for e in state.memory.entries() if e.kind == "ResearchState"]
    assert len(research_states) == 2
    assert [e.object_key for e in research_states] == ["research-state", "research-state"]
    assert [e.version for e in research_states] == [1, 2]
    assert research_states[1].supersedes == research_states[0].id


def test_approved_decisions_append_experiment_plan_memory_once():
    for option in ["approved", "approved_with_conditions"]:
        scenario = load_scenario("foam_concrete_case")
        state = _at_meeting()

        apply_decision(scenario, state, option, "同意进入最小判别实验")

        plans = [e for e in state.memory.entries() if e.kind == "ExperimentPlan"]
        assert len(plans) == 1
        payload = plans[0].payload
        plan_step = [s for s in state.steps if s.phase == "discriminating_experiment" and s.kind == "plan"][-1]
        assert payload["candidate_explanations"] == plan_step.payload["candidate_explanations"]
        assert payload["controls"] == plan_step.payload["controls"]
        assert payload["sample_chain"] == plan_step.payload["sample_chain"]
        assert payload["measurements"] == plan_step.payload["measurements"]
        assert payload["branches"] == plan_step.payload["branches"]
        assert payload["branch_effects"] == plan_step.payload["branch_effects"]
        assert payload["cost_risk"] == plan_step.payload["cost_risk"]
        assert payload["approval_option"] == option
        assert payload["approval_reason"] == "同意进入最小判别实验"
        assert payload["claim_refs"]


def test_unapproved_decisions_do_not_append_experiment_plan_memory():
    for option in ["returned", "deferred", "terminated"]:
        scenario = load_scenario("foam_concrete_case")
        state = _at_meeting()

        apply_decision(scenario, state, option, "暂不批准")

        assert [e for e in state.memory.entries() if e.kind == "ExperimentPlan"] == []
