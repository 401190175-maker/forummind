"""真组会预演的规则化点评与准备包构建。"""

from __future__ import annotations

from app.meeting_rehearsal.schemas import (
    AnswerSummary,
    MeetingRehearsalSession,
    RehearsalAnswer,
    RehearsalContext,
    RehearsalCritique,
    RehearsalQuestion,
    RehearsalQuestionFocus,
    PreparationPackage,
)


_FOCUS_GUIDANCE = {
    RehearsalQuestionFocus.BOUNDARY: (
        "说明结论适用对象、边界条件和不适用情形",
        "适用边界或反例条件仍需明确",
        "适用条件清单和边界对照表",
    ),
    RehearsalQuestionFocus.EVIDENCE: (
        "给出证据来源、样品对应关系和重复性依据",
        "证据链或样品对应关系需要补强",
        "证据引用表和样品链表",
    ),
    RehearsalQuestionFocus.EXPERIMENT: (
        "说明控制变量、测量指标和结果判定顺序",
        "判别实验的控制条件或判定顺序需要补强",
        "实验流程图、控制变量表和测量清单",
    ),
    RehearsalQuestionFocus.FALSIFICATION: (
        "明确什么结果会削弱或推翻当前解释",
        "证伪条件和替代解释仍需明确",
        "证伪条件表和结果分支图",
    ),
    RehearsalQuestionFocus.SCOPE: (
        "说明当前结论范围，并明确暂时不主张的内容",
        "研究范围和暂不主张的内容需要补强",
        "研究范围说明和术语边界表",
    ),
}


def _answers_for_question(
    question: RehearsalQuestion, answers: list[RehearsalAnswer]
) -> list[RehearsalAnswer]:
    return [answer for answer in answers if answer.question_id == question.id]


def build_critique(
    question: RehearsalQuestion,
    answers: list[RehearsalAnswer],
    context: RehearsalContext,
) -> RehearsalCritique:
    """根据问题焦点生成覆盖性反馈，不判断答案的事实正确性。"""
    guidance, weak_point, material = _FOCUS_GUIDANCE[question.focus]
    question_answers = _answers_for_question(question, answers)
    coverage_notes = [guidance]
    if not question_answers:
        coverage_notes.append("当前尚未提交应答，正式组会前需要先形成可核查的回答")
    else:
        coverage_notes.append(f"已收到 {len(question_answers)} 条应答，请逐项对应已有来源")

    if context.run_id is None:
        weak_point = f"{weak_point}；当前没有绑定 Run，需补充课题上下文"

    follow_up = f"请进一步补充：{guidance}。"
    return RehearsalCritique(
        question_id=question.id,
        coverage_notes=coverage_notes,
        weak_points=[weak_point],
        suggested_materials=[material],
        follow_up=follow_up,
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _answer_summary(question: RehearsalQuestion, answers: list[RehearsalAnswer]) -> AnswerSummary:
    question_answers = _answers_for_question(question, answers)
    return AnswerSummary(
        question_id=question.id,
        answer_ids=[answer.id for answer in question_answers],
        summary="；".join(answer.content for answer in question_answers),
        answered=bool(question_answers),
    )


def build_preparation_package(
    session: MeetingRehearsalSession,
    context: RehearsalContext,
) -> PreparationPackage:
    """从 session 快照生成结构化准备包，不修改输入。"""
    critiques = {critique.question_id: critique for critique in session.critiques}
    generated_critiques = [
        critiques.get(question.id)
        or build_critique(question, session.answers, context)
        for question in session.questions
    ]
    source_refs = _unique(
        [
            source_ref
            for question in session.questions
            for source_ref in question.source_refs
        ]
        + list(context.memory_refs)
    )
    return PreparationPackage(
        session_id=session.id,
        group_chat_id=session.group_chat_id,
        run_id=session.run_id,
        intensity=session.intensity,
        personas=list(session.personas),
        likely_questions=[question.prompt for question in session.questions],
        answer_summaries=[
            _answer_summary(question, session.answers)
            for question in session.questions
        ],
        weak_points=_unique(
            [weak_point for critique in generated_critiques for weak_point in critique.weak_points]
        ),
        suggested_materials=_unique(
            [
                material
                for critique in generated_critiques
                for material in critique.suggested_materials
            ]
        ),
        action_items=_unique(
            [
                follow_up
                for critique in generated_critiques
                if (follow_up := critique.follow_up)
            ]
        ),
        source_refs=source_refs,
        boundary_statement="模拟准备记录，不代表正式组会记录或 PI 决策",
    )
