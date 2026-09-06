"""run_import 测试。"""
import pytest

from app.orchestration.engine import apply_decision, run_import, run_replay
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario


def test_import_requires_discriminating_experiment_phase():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)
    with pytest.raises(ValueError, match="只能在 discriminating_experiment"):
        run_import(s, state)


def test_import_reaches_conclusion():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)
    apply_decision(s, state, "approved", "r")
    run_import(s, state)
    assert state.phase == "conclusion"
    assert state.status == "conclusion"
    assert any(st.kind == "hypothesis_update" for st in state.steps)
    assert any(st.kind == "conclusion" for st in state.steps)


def test_import_rejects_duplicate_results():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)
    apply_decision(s, state, "approved", "r")
    run_import(s, state)
    with pytest.raises(ValueError, match="已经导入"):
        run_import(s, state)


def test_import_appends_experiment_result_memory_with_plan_ref_only_on_success():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)
    before_illegal = len([e for e in state.memory.entries() if e.kind == "ExperimentResult"])
    with pytest.raises(ValueError, match="只能在 discriminating_experiment"):
        run_import(s, state)
    assert len([e for e in state.memory.entries() if e.kind == "ExperimentResult"]) == before_illegal

    apply_decision(s, state, "approved", "r")
    plan = [e for e in state.memory.entries() if e.kind == "ExperimentPlan"][-1]

    run_import(s, state)

    results = [e for e in state.memory.entries() if e.kind == "ExperimentResult"]
    assert len(results) == 1
    assert results[0].payload["source"] == "demo_csv"
    assert results[0].payload["rows"] == s.experiment_results.rows
    assert results[0].payload["notes"] == s.experiment_results.notes
    assert results[0].payload["validation_summary"] == s.experiment_results.validation_summary
    assert results[0].payload["plan_ref"] == plan.id

    with pytest.raises(ValueError, match="已经导入"):
        run_import(s, state)
    assert len([e for e in state.memory.entries() if e.kind == "ExperimentResult"]) == 1


def test_import_appends_hypothesis_update_memory_with_result_and_claim_refs():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)
    apply_decision(s, state, "approved", "r")

    run_import(s, state)

    entries_by_id = {e.id: e for e in state.memory.entries()}
    claim_refs_by_agent = {
        e.object_key: e.id
        for e in state.memory.entries()
        if e.kind == "Claim" and e.object_key in {u.claim_id for u in s.hypothesis_updates}
    }
    result = [e for e in state.memory.entries() if e.kind == "ExperimentResult"][-1]
    updates = [e for e in state.memory.entries() if e.kind == "HypothesisUpdate"]
    assert len(updates) == len(s.hypothesis_updates)
    assert {e.payload["claim_id"] for e in updates} == {u.claim_id for u in s.hypothesis_updates}
    for update in updates:
        payload = update.payload
        assert payload["result_ref"] == result.id
        assert payload["claim_ref"] == claim_refs_by_agent[payload["claim_id"]]
        assert payload["result_ref"] in entries_by_id
        assert payload["claim_ref"] in entries_by_id
        assert payload["causal_boundary"] == "支持程度变化不等于因果证明"


def test_import_appends_new_research_state_version_with_result_trigger():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)
    apply_decision(s, state, "approved", "r")
    before_states = [e for e in state.memory.entries() if e.kind == "ResearchState"]
    old_payload = dict(before_states[-1].payload)

    run_import(s, state)

    research_states = [e for e in state.memory.entries() if e.kind == "ResearchState"]
    result = [e for e in state.memory.entries() if e.kind == "ExperimentResult"][-1]
    assert len(research_states) == len(before_states) + 1
    assert research_states[-2].payload == old_payload
    assert research_states[-1].object_key == "research-state"
    assert research_states[-1].version == research_states[-2].version + 1
    assert research_states[-1].supersedes == research_states[-2].id
    assert research_states[-1].payload["summary"] == s.final_state.summary
    assert research_states[-1].payload["mechanism_draft"] == s.final_state.mechanism_draft
    assert research_states[-1].payload["trigger"] == "demo_experiment_result_import"
    assert research_states[-1].payload["trigger_ref"] == result.id
