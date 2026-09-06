"""真组会预演的请求、响应和内部上下文 DTO。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.domain.schemas import DataSpace

NonEmptyAnswer = Annotated[
    str,
    StringConstraints(min_length=1, max_length=4000, strip_whitespace=True),
]


class RehearsalIntensity(StrEnum):
    """质询强度。"""

    GENTLE = "gentle"
    NORMAL = "normal"
    STRICT = "strict"


class RehearsalPersona(StrEnum):
    """模拟质询对象。"""

    ADVISOR = "advisor"
    PEER = "peer"
    COMMITTEE = "committee"
    MIXED = "mixed"


class RehearsalQuestionFocus(StrEnum):
    """质询关注点。"""

    BOUNDARY = "boundary"
    EVIDENCE = "evidence"
    EXPERIMENT = "experiment"
    FALSIFICATION = "falsification"
    SCOPE = "scope"


class RehearsalQuestionStatus(StrEnum):
    """问题的应答状态。"""

    PENDING = "pending"
    ANSWERED = "answered"


class RehearsalSessionStatus(StrEnum):
    """预演会话状态。"""

    ACTIVE = "active"
    COMPLETED = "completed"
    CLOSED = "closed"


class CreateMeetingRehearsalRequest(BaseModel):
    """创建预演会话请求。"""

    run_id: str | None = None
    intensity: RehearsalIntensity = RehearsalIntensity.NORMAL
    personas: list[RehearsalPersona] = Field(
        default_factory=lambda: [
            RehearsalPersona.ADVISOR,
            RehearsalPersona.PEER,
        ]
    )
    max_questions: int = Field(default=5, ge=3, le=10)

    @field_validator("personas")
    @classmethod
    def _require_persona(cls, value: list[RehearsalPersona]) -> list[RehearsalPersona]:
        if not value:
            raise ValueError("personas 至少需要一个模拟对象")
        return value


class SubmitRehearsalAnswerRequest(BaseModel):
    """提交预演应答请求。"""

    question_id: str = Field(min_length=1)
    answer: NonEmptyAnswer


class RehearsalContext(BaseModel):
    """创建时冻结的最小只读研究上下文，不直接作为 HTTP 响应。"""

    group_chat_id: str
    topic_name: str
    topic_summary: str
    run_id: str | None = None
    run_phase: str | None = None
    run_cycle: int | None = None
    step_summaries: list[dict] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    memory_view_summaries: list[dict] = Field(default_factory=list)
    scenario_summary: str = ""
    data_space: DataSpace = DataSpace.SYNTHETIC


class RehearsalQuestion(BaseModel):
    """预演中的一条确定性质询。"""

    id: str
    sequence: int = Field(ge=1)
    persona: RehearsalPersona
    prompt: NonEmptyAnswer
    source_refs: list[str] = Field(default_factory=list)
    focus: RehearsalQuestionFocus
    status: RehearsalQuestionStatus = RehearsalQuestionStatus.PENDING


class RehearsalAnswer(BaseModel):
    """用户提交的一条预演应答。"""

    id: str
    question_id: str
    content: NonEmptyAnswer
    created_at: float = 0.0
    data_space: DataSpace = DataSpace.SYNTHETIC


class RehearsalCritique(BaseModel):
    """规则化的覆盖性反馈，不是事实正确性评分。"""

    question_id: str
    coverage_notes: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    suggested_materials: list[str] = Field(default_factory=list)
    follow_up: str | None = None
    is_factual_grade: Literal[False] = False


class AnswerSummary(BaseModel):
    """准备包中的问题应答摘要。"""

    question_id: str
    answer_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    answered: bool = False


class PreparationPackage(BaseModel):
    """真组会准备包，属于预演记录而非正式会议产物。"""

    session_id: str
    group_chat_id: str
    run_id: str | None = None
    intensity: RehearsalIntensity = RehearsalIntensity.NORMAL
    personas: list[RehearsalPersona] = Field(default_factory=list)
    likely_questions: list[str] = Field(default_factory=list)
    answer_summaries: list[AnswerSummary] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    suggested_materials: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    data_space: DataSpace = DataSpace.SYNTHETIC
    record_scope: Literal["rehearsal"] = "rehearsal"
    persistence: Literal["not_persisted"] = "not_persisted"
    boundary_statement: str


class MeetingRehearsalSession(BaseModel):
    """预演会话的公开快照。"""

    id: str
    group_chat_id: str
    run_id: str | None = None
    status: RehearsalSessionStatus = RehearsalSessionStatus.ACTIVE
    intensity: RehearsalIntensity = RehearsalIntensity.NORMAL
    personas: list[RehearsalPersona] = Field(
        default_factory=lambda: [
            RehearsalPersona.ADVISOR,
            RehearsalPersona.PEER,
        ]
    )
    questions: list[RehearsalQuestion] = Field(default_factory=list)
    answers: list[RehearsalAnswer] = Field(default_factory=list)
    critiques: list[RehearsalCritique] = Field(default_factory=list)
    preparation_package: PreparationPackage | None = None
    data_space: DataSpace = DataSpace.SYNTHETIC
    record_scope: Literal["rehearsal"] = "rehearsal"
    persistence: Literal["not_persisted"] = "not_persisted"
    created_at: float = 0.0
    updated_at: float = 0.0
