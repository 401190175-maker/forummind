"""真组会预演准备包构建测试（tasks.md Task 4）。"""

from app.meeting_rehearsal.package_builder import (
    build_critique,
    build_preparation_package,
)
from app.meeting_rehearsal.schemas import (
    MeetingRehearsalSession,
    RehearsalAnswer,
    RehearsalContext,
    RehearsalCritique,
    RehearsalIntensity,
    RehearsalPersona,
    RehearsalQuestion,
    RehearsalQuestionFocus,
    RehearsalQuestionStatus,
)


def _context() -> RehearsalContext:
    return RehearsalContext(
        group_chat_id="gc-1",
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="验证泥浆条件、气泡稳定与孔结构的关系",
        run_id="run-1",
        run_phase="meeting",
        run_cycle=1,
        step_summaries=[
            {
                "id": "step-review",
                "phase": "review_gate",
                "kind": "review_opinion",
                "actor": "agent-phd-1",
                "content": "样品对应关系缺失",
                "payload": {"kind": "missing_observation"},
                "timestamp": 1.0,
            }
        ],
        memory_refs=["mem-1"],
        memory_view_summaries=[],
    )


def _question(question_id: str, sequence: int, focus: RehearsalQuestionFocus) -> RehearsalQuestion:
    return RehearsalQuestion(
        id=question_id,
        sequence=sequence,
        persona=RehearsalPersona.ADVISOR,
        prompt=f"问题 {sequence}",
        source_refs=["step-review"],
        focus=focus,
    )


def test_critique_is_coverage_guidance_not_factual_grading() -> None:
    question = _question("question-1", 1, RehearsalQuestionFocus.EVIDENCE)
    answer = RehearsalAnswer(
        id="answer-1",
        question_id="question-1",
        content="我会补齐同批样品的对应关系。",
    )

    critique = build_critique(question, [answer], _context())

    assert critique.question_id == "question-1"
    assert critique.coverage_notes
    assert critique.weak_points
    assert critique.suggested_materials
    assert critique.is_factual_grade is False


def test_package_aligns_answers_and_keeps_unanswered_questions() -> None:
    first = _question("question-1", 1, RehearsalQuestionFocus.EVIDENCE)
    second = _question("question-2", 2, RehearsalQuestionFocus.EXPERIMENT)
    answers = [
        RehearsalAnswer(
            id="answer-1",
            question_id="question-1",
            content="先补齐样品链。",
            created_at=1.0,
        ),
        RehearsalAnswer(
            id="answer-2",
            question_id="question-1",
            content="再核对控制变量。",
            created_at=2.0,
        ),
    ]
    session = MeetingRehearsalSession(
        id="rehearsal-1",
        group_chat_id="gc-1",
        run_id="run-1",
        intensity=RehearsalIntensity.NORMAL,
        personas=[RehearsalPersona.ADVISOR],
        questions=[first, second],
        answers=answers,
        critiques=[
            RehearsalCritique(
                question_id="question-1",
                weak_points=["需要说明配对关系"],
                suggested_materials=["样品链表"],
            )
        ],
    )

    package = build_preparation_package(session, _context())

    assert package.likely_questions == ["问题 1", "问题 2"]
    assert package.answer_summaries[0].answer_ids == ["answer-1", "answer-2"]
    assert package.answer_summaries[0].answered is True
    assert package.answer_summaries[1].answer_ids == []
    assert package.answer_summaries[1].answered is False
    assert "需要说明配对关系" in package.weak_points
    assert "样品链表" in package.suggested_materials
    assert "step-review" in package.source_refs
    assert package.record_scope == "rehearsal"
    assert package.persistence == "not_persisted"


def test_package_does_not_mutate_session_lists() -> None:
    question = _question("question-1", 1, RehearsalQuestionFocus.BOUNDARY)
    session = MeetingRehearsalSession(
        id="rehearsal-1",
        group_chat_id="gc-1",
        questions=[question],
    )
    original_questions = session.model_dump(mode="json")["questions"]

    build_preparation_package(session, _context())

    assert session.model_dump(mode="json")["questions"] == original_questions
