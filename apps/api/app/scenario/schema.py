"""Scenario 剧本契约：价值链各阶段的确定性真源（自包含，不导入领域层）。v2：cycles 结构。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PreviewQuestion(BaseModel):
    question_id: str
    question: str
    hint: str


class MasterClaim(BaseModel):
    statement: str
    evidence_refs: list[str] = Field(default_factory=list)
    boundary: str
    prediction: str
    falsification_condition: str


class Master(BaseModel):
    agent_id: str
    capability: str
    claim: MasterClaim


class DiscussionTurn(BaseModel):
    speaker: str
    kind: Literal["proposal", "attack", "response", "revision", "collaborate"]
    content: str
    seat: Literal["proposal_owner", "discriminability", "feasibility_evidence"] | None = None


class DiscussionSession(BaseModel):
    session_id: str
    kind: Literal["adversarial", "collaborative"]
    initiator: str
    trigger: Literal["uncertain_claim", "hard_evidence", "review_conflict"]
    participants: list[str]
    turns: list[DiscussionTurn]


class PostdocExchange(BaseModel):
    requester: str | None = None
    speaker: str
    kind: Literal["request", "in_scope_answer", "out_of_scope_refusal"]
    content: str
    sources: list[str] = Field(default_factory=list)


class ReviewItem(BaseModel):
    kind: Literal["counterexample", "falsification_condition", "missing_observation"]
    content: str


class Disposition(BaseModel):
    kind: Literal["counterexample", "falsification_condition", "missing_observation"]
    content: str
    actor: str
    disposition: Literal["accepted", "rejected"]
    reason: str


class ReviewGate(BaseModel):
    reviewer: str
    items: list[ReviewItem]


class Decision(BaseModel):
    actor: str
    option: Literal["approved", "approved_with_conditions", "returned", "deferred", "terminated"]
    reason: str


class Meeting(BaseModel):
    agenda: list[str]
    unresolved_disagreements: list[str]
    suggested_decision: Decision
    action_items: list[str]


class MeetingCycle(BaseModel):
    cycle: int
    scheduled_for: str
    masters: list[Master]
    discussion_sessions: list[DiscussionSession] = Field(default_factory=list)
    postdoc_exchange: list[PostdocExchange] = Field(default_factory=list)
    review_gate: ReviewGate
    review_triggered_sessions: list[DiscussionSession] = Field(default_factory=list)
    dispositions: list[Disposition] = Field(default_factory=list)
    meeting: Meeting


class DiscriminatingExperiment(BaseModel):
    controls: list[str]
    sample_chain: str
    measurements: list[str]
    branches: list[str]
    candidate_explanations: list[str] = Field(default_factory=list)
    branch_effects: list[str] = Field(default_factory=list)
    cost_risk: str


class ExperimentResults(BaseModel):
    source: str
    rows: list[dict]
    notes: str
    validation_summary: str = ""


class HypothesisUpdate(BaseModel):
    claim_id: str
    status: Literal["supported", "weakened", "inconclusive", "posterior"]
    reason: str


class FinalState(BaseModel):
    summary: str
    mechanism_draft: str


class Scenario(BaseModel):
    package_id: str
    data_space: Literal["synthetic"] = "synthetic"
    cycles: list[MeetingCycle]
    discriminating_experiment: DiscriminatingExperiment
    experiment_results: ExperimentResults
    hypothesis_updates: list[HypothesisUpdate]
    final_state: FinalState
    preview_questions: list[PreviewQuestion] = Field(default_factory=list)
