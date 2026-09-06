"""真组会预演 DTO 契约测试（tasks.md Task 1）。"""

import pytest
from pydantic import ValidationError

from app.meeting_rehearsal.schemas import (
    CreateMeetingRehearsalRequest,
    MeetingRehearsalSession,
    PreparationPackage,
    RehearsalCritique,
    SubmitRehearsalAnswerRequest,
)


def test_create_request_defaults_to_normal_mixed_personas_and_five_questions() -> None:
    request = CreateMeetingRehearsalRequest.model_validate({})

    assert request.run_id is None
    assert request.intensity.value == "normal"
    assert [persona.value for persona in request.personas] == ["advisor", "peer"]
    assert request.max_questions == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"intensity": "aggressive"},
        {"personas": []},
        {"max_questions": 2},
        {"max_questions": 11},
    ],
)
def test_create_request_rejects_invalid_rehearsal_options(payload: dict) -> None:
    with pytest.raises(ValidationError):
        CreateMeetingRehearsalRequest.model_validate(payload)


def test_answer_request_trims_content_and_rejects_blank_content() -> None:
    request = SubmitRehearsalAnswerRequest.model_validate(
        {"question_id": "question-1", "answer": "  解释样品链和控制变量  "}
    )

    assert request.answer == "解释样品链和控制变量"

    with pytest.raises(ValidationError):
        SubmitRehearsalAnswerRequest.model_validate(
            {"question_id": "question-1", "answer": "   "}
        )


def test_rehearsal_session_and_package_have_boundary_defaults() -> None:
    session = MeetingRehearsalSession(
        id="rehearsal-1",
        group_chat_id="gc-1",
        questions=[],
    )
    package = PreparationPackage(
        session_id="rehearsal-1",
        group_chat_id="gc-1",
        likely_questions=[],
        answer_summaries=[],
        weak_points=[],
        suggested_materials=[],
        action_items=[],
        source_refs=[],
        boundary_statement="模拟准备记录，不代表正式组会记录或 PI 决策",
    )
    critique = RehearsalCritique(question_id="question-1")

    assert session.data_space.value == "synthetic"
    assert session.record_scope == "rehearsal"
    assert session.persistence == "not_persisted"
    assert package.data_space.value == "synthetic"
    assert package.record_scope == "rehearsal"
    assert package.persistence == "not_persisted"
    assert critique.is_factual_grade is False


def test_rehearsal_list_defaults_are_independent() -> None:
    first = MeetingRehearsalSession(id="rehearsal-1", group_chat_id="gc-1")
    second = MeetingRehearsalSession(id="rehearsal-2", group_chat_id="gc-1")

    first.answers.append({"id": "answer-1"})

    assert second.answers == []
