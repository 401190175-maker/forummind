"""只读实验视图投影测试。"""
from copy import deepcopy

from app.memory.timeline import MemoryEntry
from app.orchestration.engine import apply_decision, run_import, run_replay
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario


def _run_to_experiment():
    store = RunStore()
    state = store.create("gc-1", "replay")
    scenario = load_scenario("foam_concrete_case")
    run_replay(scenario, state)
    apply_decision(scenario, state, "approved_with_conditions", "按条件批准")
    return scenario, state


def test_experiment_view_empty_state_has_stable_shape():
    from app.memory.experiment_projection import build_experiment_view

    view = build_experiment_view(phase="meeting", steps=[], entries=[])

    assert set(view) == {
        "data_space",
        "phase",
        "plan",
        "results",
        "hypothesis_updates",
        "research_state_change",
        "boundary_notes",
    }
    assert view["data_space"] == "synthetic"
    assert view["phase"] == "meeting"
    assert view["plan"] is None
    assert view["results"] is None
    assert view["hypothesis_updates"] == []
    assert view["research_state_change"] is None
    assert any("AI 不执行真实实验" in note for note in view["boundary_notes"])
    assert any("符合预测不等于证明因果" in note for note in view["boundary_notes"])


def test_experiment_view_projects_plan_and_approval_boundary_without_mutating_inputs():
    from app.memory.experiment_projection import build_experiment_view

    scenario, state = _run_to_experiment()
    steps_before = deepcopy(state.steps)
    entries = state.memory.entries()
    entries_before = deepcopy(entries)

    view = build_experiment_view(phase=state.phase, steps=state.steps, entries=entries)

    assert state.steps == steps_before
    assert entries == entries_before
    assert view["phase"] == "discriminating_experiment"
    assert view["data_space"] == "synthetic"
    assert view["results"] is None
    assert view["research_state_change"] is None
    assert view["hypothesis_updates"] == []
    assert view["plan"] == {
        "title": "最小判别实验方案",
        "candidate_explanations": scenario.discriminating_experiment.candidate_explanations,
        "controls": scenario.discriminating_experiment.controls,
        "sample_chain": scenario.discriminating_experiment.sample_chain,
        "measurements": scenario.discriminating_experiment.measurements,
        "branches": scenario.discriminating_experiment.branches,
        "branch_effects": scenario.discriminating_experiment.branch_effects,
        "cost_risk": scenario.discriminating_experiment.cost_risk,
        "approval_boundary": {
            "option": "approved_with_conditions",
            "reason": "按条件批准",
        },
    }


def test_experiment_view_plan_tolerates_non_dict_memory_payload():
    from app.memory.experiment_projection import build_experiment_view

    entry = MemoryEntry(
        id="mem-plan",
        kind="ExperimentPlan",
        payload="bad payload",
        version=1,
        supersedes=None,
        created_at=1.0,
    )

    view = build_experiment_view(phase="discriminating_experiment", steps=[], entries=[entry])

    assert view["plan"] == {
        "title": "最小判别实验方案",
        "candidate_explanations": [],
        "controls": [],
        "sample_chain": "—",
        "measurements": [],
        "branches": [],
        "branch_effects": [],
        "cost_risk": "—",
        "approval_boundary": None,
    }


def test_experiment_view_projects_import_results_updates_and_research_state_change():
    from app.memory.experiment_projection import build_experiment_view

    scenario, state = _run_to_experiment()

    run_import(scenario, state)

    view = build_experiment_view(
        phase=state.phase,
        steps=state.steps,
        entries=state.memory.entries(),
    )
    research_states = [e for e in state.memory.entries() if e.kind == "ResearchState"]
    assert view["results"] == {
        "source": scenario.experiment_results.source,
        "rows": scenario.experiment_results.rows,
        "notes": scenario.experiment_results.notes,
        "validation_summary": scenario.experiment_results.validation_summary,
        "imported_at": [s for s in state.steps if s.kind == "results"][-1].timestamp,
    }
    assert view["hypothesis_updates"] == [
        {
            "claim_id": update.claim_id,
            "status": update.status,
            "reason": update.reason,
            "causal_boundary": "支持程度变化不等于因果证明",
        }
        for update in scenario.hypothesis_updates
    ]
    assert view["research_state_change"] == {
        "previous_ref": research_states[-2].id,
        "current_ref": research_states[-1].id,
        "summary": scenario.final_state.summary,
        "trigger": "demo_experiment_result_import",
        "supersedes": True,
        "preserves_old_version": True,
    }


def test_experiment_view_tolerates_malformed_import_payloads():
    from app.memory.experiment_projection import build_experiment_view

    entries = [
        MemoryEntry(
            id="mem-result",
            kind="ExperimentResult",
            payload="bad",
            version=1,
            supersedes=None,
            created_at=1.0,
        ),
        MemoryEntry(
            id="mem-update",
            kind="HypothesisUpdate",
            payload={"claim_id": "agent-ms-1"},
            version=1,
            supersedes=None,
            created_at=2.0,
        ),
        MemoryEntry(
            id="mem-state",
            kind="ResearchState",
            payload={"summary": "new"},
            version=1,
            supersedes=None,
            created_at=3.0,
            object_key="research-state",
        ),
    ]

    view = build_experiment_view(phase="conclusion", steps=[], entries=entries)

    assert view["results"] == {
        "source": "—",
        "rows": [],
        "notes": "—",
        "validation_summary": "—",
        "imported_at": None,
    }
    assert view["hypothesis_updates"] == [{
        "claim_id": "agent-ms-1",
        "status": "inconclusive",
        "reason": "—",
        "causal_boundary": "支持程度变化不等于因果证明",
    }]
    assert view["research_state_change"] == {
        "previous_ref": None,
        "current_ref": "mem-state",
        "summary": "new",
        "trigger": "—",
        "supersedes": False,
        "preserves_old_version": True,
    }
