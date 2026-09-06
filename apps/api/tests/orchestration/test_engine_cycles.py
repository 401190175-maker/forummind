"""两 cycle 循环 + import 测试。"""
from app.orchestration.engine import apply_decision, run_import, run_replay
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario


def test_two_cycles_then_approve_then_import():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)                              # cycle1 → meeting
    apply_decision(s, state, "returned", "证据不足")   # cycle2
    run_replay(s, state)                              # cycle2 → meeting
    assert state.cycle == 2
    apply_decision(s, state, "approved_with_conditions", "r")  # → 判别实验
    run_import(s, state)                              # → conclusion
    assert state.phase == "conclusion"
    claims = [e for e in state.memory.entries() if e.kind == "Claim"]
    assert any(e.supersedes for e in claims)  # v1→v2→v3→v4 版本链
    assert any(e.kind == "ResearchState" for e in state.memory.entries())
    assert any(e.kind == "Decision" for e in state.memory.entries())


def test_claim_versions_follow_same_agent_across_cycles():
    store = RunStore()
    state = store.create("gc-1", "replay")
    s = load_scenario("foam_concrete_case")
    run_replay(s, state)
    apply_decision(s, state, "returned", "证据不足")
    agent_claims = [
        e for e in state.memory.entries()
        if e.kind == "Claim" and e.payload.get("agent_id") == "agent-ms-1"
    ]
    assert [e.version for e in agent_claims] == [1, 2, 3, 4]
    assert agent_claims[1].supersedes == agent_claims[0].id
    assert agent_claims[2].supersedes == agent_claims[1].id
    assert agent_claims[3].supersedes == agent_claims[2].id
