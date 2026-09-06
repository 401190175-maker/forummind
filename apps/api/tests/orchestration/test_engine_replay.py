"""run_replay 单 cycle 全链测试。"""
from app.orchestration.engine import run_replay
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario


def _new_replay():
    store = RunStore()
    state = store.create("gc-1", "replay")
    return store, state


def test_analysis_emits_three_claims():
    _, state = _new_replay()
    run_replay(load_scenario("foam_concrete_case"), state)
    claims = [s for s in state.steps if s.kind == "claim"]
    assert len(claims) == 3
    assert any(e.kind == "Claim" and e.payload.get("status") == "initial"
               for e in state.memory.entries())


def test_full_cycle_phase_order_and_freeze():
    _, state = _new_replay()
    run_replay(load_scenario("foam_concrete_case"), state)
    phases = [s.phase for s in state.steps]
    for p in ["independent_analysis", "discussion", "review_gate",
              "review_triggered_debate", "revision", "freeze", "meeting"]:
        assert p in phases
    assert state.status == "awaiting_decision"
    assert state.phase == "meeting"
    frozen = [e for e in state.memory.entries()
              if e.kind == "Claim" and e.payload.get("status") == "frozen"]
    assert len(frozen) == 3
    assert any(s.kind == "freeze" and s.payload.get("frozen_at") == "meeting-1h"
               for s in state.steps)
    assert not any(e.kind == "Decision" for e in state.memory.entries())


def test_review_gate_has_counterexample_step():
    _, state = _new_replay()
    run_replay(load_scenario("foam_concrete_case"), state)
    opinions = [s for s in state.steps if s.kind == "review_opinion"]
    assert any(s.payload.get("kind") == "counterexample" for s in opinions)


def test_postdoc_exchange_is_emitted_to_steps_and_memory():
    _, state = _new_replay()
    run_replay(load_scenario("foam_concrete_case"), state)
    exchanges = [s for s in state.steps if s.phase == "postdoc_exchange"]
    assert any(s.kind == "in_scope_answer" for s in exchanges)
    assert any(s.kind == "out_of_scope_refusal" for s in exchanges)
    assert any(e.kind == "PostdocExchange" for e in state.memory.entries())


def test_revision_emits_dispositions():
    _, state = _new_replay()
    run_replay(load_scenario("foam_concrete_case"), state)
    assert len([s for s in state.steps if s.kind == "disposition"]) == 3
    assert any(e.kind == "Disposition" for e in state.memory.entries())


def test_discussion_session_has_initiator_and_trigger():
    _, state = _new_replay()
    run_replay(load_scenario("foam_concrete_case"), state)
    sessions = [s for s in state.steps if s.kind == "session" and s.phase == "discussion"]
    assert sessions and sessions[0].payload.get("initiator") == "agent-ms-1"
    assert sessions[0].payload.get("trigger") == "uncertain_claim"
