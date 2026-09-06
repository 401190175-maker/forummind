"""真组会预演确定性问题库测试（tasks.md Task 3）。"""

from app.meeting_rehearsal.question_bank import generate_questions
from app.meeting_rehearsal.schemas import (
    RehearsalContext,
    RehearsalIntensity,
    RehearsalPersona,
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
                "content": "强度、孔结构与反应表征的样品对应关系缺失",
                "payload": {"kind": "missing_observation"},
                "timestamp": 1.0,
            },
            {
                "id": "step-meeting",
                "phase": "meeting",
                "kind": "unresolved",
                "actor": "system",
                "content": "控制新拌差异后强度差异是否仍保留",
                "payload": {},
                "timestamp": 2.0,
            },
        ],
        memory_refs=["mem-claim-1"],
        memory_view_summaries=[
            {
                "id": "mem-claim-1",
                "kind": "Claim",
                "summary": "含泡样品需要可重复的配对观测",
            }
        ],
        scenario_summary="先补齐样品链和控制条件，再检验机制路径。",
    )


def test_question_bank_is_deterministic_and_has_at_least_three_questions() -> None:
    arguments = (_context(), RehearsalIntensity.NORMAL, [RehearsalPersona.ADVISOR], 5)

    first = generate_questions(*arguments)
    second = generate_questions(*arguments)

    assert first == second
    assert 3 <= len(first) <= 5
    assert [question.sequence for question in first] == list(range(1, len(first) + 1))
    assert all(question.status.value == "pending" for question in first)


def test_questions_prioritize_review_and_meeting_sources() -> None:
    questions = generate_questions(
        _context(),
        RehearsalIntensity.NORMAL,
        [RehearsalPersona.ADVISOR, RehearsalPersona.PEER],
        5,
    )

    source_refs = {ref for question in questions for ref in question.source_refs}
    prompts = "\n".join(question.prompt for question in questions)

    assert "step-review" in source_refs
    assert "step-meeting" in source_refs
    assert "样品" in prompts or "控制" in prompts


def test_mixed_persona_is_normalized_to_concrete_question_personas() -> None:
    questions = generate_questions(
        _context(),
        RehearsalIntensity.STRICT,
        [RehearsalPersona.MIXED],
        6,
    )

    assert questions
    assert all(question.persona is not RehearsalPersona.MIXED for question in questions)


def test_no_run_context_uses_scenario_fallback_questions() -> None:
    context = _context().model_copy(
        update={
            "run_id": None,
            "run_phase": None,
            "run_cycle": None,
            "step_summaries": [],
            "memory_refs": [],
            "memory_view_summaries": [],
        }
    )

    questions = generate_questions(
        context,
        RehearsalIntensity.GENTLE,
        [RehearsalPersona.PEER],
        3,
    )

    assert len(questions) == 3
    assert all(question.source_refs == [] for question in questions)
    assert all(question.prompt.strip() for question in questions)
