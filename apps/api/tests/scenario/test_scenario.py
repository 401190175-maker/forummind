"""Scenario 剧本模块单元测试（v2：cycles 结构）。"""
import pytest
from pydantic import ValidationError

from app.scenario.schema import (
    Decision,
    DiscriminatingExperiment,
    Disposition,
    DiscussionSession,
    DiscussionTurn,
    ExperimentResults,
    FinalState,
    HypothesisUpdate,
    Master,
    MasterClaim,
    Meeting,
    MeetingCycle,
    PostdocExchange,
    PreviewQuestion,
    ReviewGate,
    ReviewItem,
    Scenario,
)


def test_package_importable():
    import app.scenario  # noqa: F401


# --- 基础子模型 ---

def test_preview_question_fields():
    pq = PreviewQuestion(question_id="pq-1", question="控制新拌差异后强度差异是否仍保留？", hint="证据缺口")
    assert pq.question_id == "pq-1"
    assert pq.hint == "证据缺口"


def test_master_claim_requires_all_fields():
    with pytest.raises(ValidationError):
        MasterClaim(statement="x")


def test_master_fields():
    m = Master(agent_id="agent-ms-1", capability="文献与机制分析",
               claim=MasterClaim(statement="s", boundary="b", prediction="p",
                                 falsification_condition="f"))
    assert m.agent_id == "agent-ms-1"
    assert m.claim.statement == "s"


# --- 讨论模型（v2） ---

def test_discussion_turn_kind_literal():
    with pytest.raises(ValidationError):
        DiscussionTurn(speaker="agent-ms-1", kind="praise", content="x")
    DiscussionTurn(speaker="agent-ms-1", kind="collaborate", content="x")  # 协作合法


def test_discussion_turn_seat_optional():
    t = DiscussionTurn(speaker="agent-ms-1", kind="collaborate", content="x")
    assert t.seat is None


def test_discussion_session_fields():
    s = DiscussionSession(session_id="ds-1", kind="adversarial",
                          initiator="agent-ms-1", trigger="uncertain_claim",
                          participants=["agent-ms-1", "agent-ms-2"],
                          turns=[DiscussionTurn(speaker="agent-ms-1", kind="proposal",
                                                seat="proposal_owner", content="方案")])
    assert s.session_id == "ds-1"
    assert s.kind == "adversarial"
    assert s.initiator == "agent-ms-1"
    assert s.trigger == "uncertain_claim"
    assert s.turns[0].seat == "proposal_owner"


# --- 审查模型 ---

def test_review_item_opinion_only():
    r = ReviewItem(kind="counterexample", content="无泡流变数据不能直接迁移到含泡体系。")
    assert r.kind == "counterexample"
    assert not hasattr(r, "disposition")  # 意见对象不含处置字段


def test_disposition_literal():
    with pytest.raises(ValidationError):
        Disposition(kind="counterexample", content="x", disposition="maybe", reason="r")


def test_disposition_fields():
    d = Disposition(kind="counterexample", content="x", actor="agent-ms-1",
                    disposition="accepted", reason="r")
    assert d.disposition == "accepted"
    assert d.actor == "agent-ms-1"
    assert d.reason == "r"


def test_review_gate_holds_items():
    g = ReviewGate(reviewer="agent-phd-1", items=[
        ReviewItem(kind="counterexample", content="无泡流变数据不能直接迁移到含泡体系。"),
    ])
    assert g.reviewer == "agent-phd-1"
    assert g.items[0].kind == "counterexample"


def test_postdoc_kind_literal():
    with pytest.raises(ValidationError):
        PostdocExchange(speaker="agent-postdoc-1", kind="guess", content="x")


# --- 组会与实验模型 ---

def test_decision_option_literal():
    with pytest.raises(ValidationError):
        Decision(actor="PI", option="maybe", reason="r")


def test_decision_five_options_allowed():
    for opt in ["approved", "approved_with_conditions", "returned", "deferred", "terminated"]:
        Decision(actor="PI", option=opt, reason="r")


def test_meeting_has_suggested_decision():
    m = Meeting(agenda=[], unresolved_disagreements=[],
                suggested_decision=Decision(actor="PI", option="approved", reason="r"),
                action_items=[])
    assert m.suggested_decision.option == "approved"
    assert not hasattr(m, "decision")


def test_hypothesis_status_literal():
    with pytest.raises(ValidationError):
        HypothesisUpdate(claim_id="agent-ms-1", status="proven", reason="r")


def test_experiment_fields():
    e = DiscriminatingExperiment(
        controls=["泥浆掺量"], sample_chain="同一试件或配对试件",
        measurements=["孔结构"], branches=["新拌—孔结构路径占主导"],
        candidate_explanations=["泥浆改变含泡体系路径"],
        branch_effects=["上调该路径的支持程度"],
        cost_risk="低")
    assert "新拌—孔结构路径占主导" in e.branches


def test_experiment_display_contract_fields_are_present():
    s = load_scenario("foam_concrete_case")
    experiment = s.discriminating_experiment
    assert experiment.candidate_explanations
    assert experiment.branch_effects
    assert len(experiment.branch_effects) == len(experiment.branches)
    assert s.experiment_results.validation_summary


def test_final_state_fields():
    f = FinalState(summary="s", mechanism_draft="draft")
    assert f.mechanism_draft == "draft"


# --- Scenario 主模型（v2） ---

def _minimal_cycle(cycle: int) -> MeetingCycle:
    return MeetingCycle(
        cycle=cycle,
        scheduled_for=f"第 {cycle} 周组会",
        masters=[],
        review_gate=ReviewGate(reviewer="agent-phd-1", items=[]),
        meeting=Meeting(agenda=[], unresolved_disagreements=[],
                        suggested_decision=Decision(actor="PI", option="approved", reason="r"),
                        action_items=[]),
    )


def _minimal_scenario(**overrides):
    base = dict(
        package_id="foam_concrete_case",
        cycles=[_minimal_cycle(1), _minimal_cycle(2)],
        discriminating_experiment=DiscriminatingExperiment(
            controls=[], sample_chain="", measurements=[], branches=[], cost_risk=""),
        experiment_results=ExperimentResults(source="demo_csv", rows=[], notes=""),
        hypothesis_updates=[],
        final_state=FinalState(summary="", mechanism_draft=""),
        preview_questions=[PreviewQuestion(question_id="pq-1", question="q", hint="h")],
    )
    base.update(overrides)
    return Scenario(**base)


def test_scenario_has_two_cycles():
    s = _minimal_scenario()
    assert len(s.cycles) == 2


def test_scenario_data_space_literal():
    with pytest.raises(ValidationError):
        _minimal_scenario(data_space="real")


# --- loader 契约 ---

from app.scenario.loader import ScenarioNotFound, load_scenario  # noqa: E402


def test_three_masters_distinct_capabilities():
    s = load_scenario("foam_concrete_case")
    assert len({m.capability for m in s.cycles[0].masters}) == 3


def test_review_gate_has_counterexample():
    s = load_scenario("foam_concrete_case")
    assert "counterexample" in {i.kind for i in s.cycles[0].review_gate.items}


def test_dispositions_present():
    s = load_scenario("foam_concrete_case")
    assert len(s.cycles[0].dispositions) == 3
    assert all(d.disposition == "accepted" for d in s.cycles[0].dispositions)
    assert len(s.cycles[1].dispositions) == 3


def test_discussion_sessions_have_initiator_and_trigger():
    s = load_scenario("foam_concrete_case")
    ds1 = s.cycles[0].discussion_sessions[0]
    assert ds1.initiator == "agent-ms-1"
    assert ds1.trigger == "uncertain_claim"
    rt1 = s.cycles[0].review_triggered_sessions[0]
    assert rt1.initiator == "agent-phd-1"
    assert rt1.trigger == "review_conflict"
    ds3 = s.cycles[1].discussion_sessions[0]
    assert ds3.initiator == "agent-ms-3"
    assert ds3.trigger == "hard_evidence"


def test_cycles_have_scheduled_meeting():
    s = load_scenario("foam_concrete_case")
    assert s.cycles[0].scheduled_for == "第 1 周组会"
    assert s.cycles[1].scheduled_for == "第 2 周组会"


def test_cycle1_returned_cycle2_approved():
    s = load_scenario("foam_concrete_case")
    assert s.cycles[0].meeting.suggested_decision.option == "returned"
    assert s.cycles[1].meeting.suggested_decision.option == "approved_with_conditions"


def test_unknown_package_raises():
    with pytest.raises(ScenarioNotFound):
        load_scenario("nope")


def test_scenario_is_synthetic():
    s = load_scenario("foam_concrete_case")
    assert s.data_space == "synthetic"


def test_preview_questions_present():
    s = load_scenario("foam_concrete_case")
    assert len(s.preview_questions) >= 3
    assert all(pq.question_id and pq.question and pq.hint for pq in s.preview_questions)


# --- 导出契约 ---

def test_exports_available():
    from app.scenario import Scenario as S, ScenarioNotFound as E, load_scenario as L

    assert callable(L)
    assert issubclass(E, KeyError)
    assert S is not None
