"""真组会预演的确定性问题生成。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.meeting_rehearsal.schemas import (
    RehearsalContext,
    RehearsalIntensity,
    RehearsalPersona,
    RehearsalQuestion,
    RehearsalQuestionFocus,
)


@dataclass(frozen=True)
class _QuestionCandidate:
    prompt: str
    focus: RehearsalQuestionFocus
    source_ref: str | None = None


def _step_candidates(context: RehearsalContext) -> list[_QuestionCandidate]:
    candidates: list[_QuestionCandidate] = []
    for step in context.step_summaries:
        step_id = step.get("id")
        phase = step.get("phase")
        kind = step.get("kind")
        content = str(step.get("content") or "").strip()
        if not content:
            continue

        source_ref = step_id if isinstance(step_id, str) and step_id else None
        if phase == "review_gate":
            focus = {
                "counterexample": RehearsalQuestionFocus.BOUNDARY,
                "falsification_condition": RehearsalQuestionFocus.FALSIFICATION,
                "missing_observation": RehearsalQuestionFocus.EVIDENCE,
            }.get(str(step.get("payload", {}).get("kind")), RehearsalQuestionFocus.EVIDENCE)
            candidates.append(
                _QuestionCandidate(
                    f"针对审查意见“{content}”，你准备如何补齐证据，并说明它的适用边界？",
                    focus,
                    source_ref,
                )
            )
        elif phase == "meeting" and kind == "unresolved":
            candidates.append(
                _QuestionCandidate(
                    f"组会尚未解决的问题是“{content}”。你会用什么可判别的观测或实验把不同解释区分开？",
                    RehearsalQuestionFocus.EXPERIMENT,
                    source_ref,
                )
            )
        elif kind == "claim":
            candidates.append(
                _QuestionCandidate(
                    f"关于当前观点“{content}”，它的可证伪条件是什么？什么结果会迫使你修改判断？",
                    RehearsalQuestionFocus.FALSIFICATION,
                    source_ref,
                )
            )

    return candidates


def _memory_candidates(context: RehearsalContext) -> list[_QuestionCandidate]:
    return [
        _QuestionCandidate(
            f"已有研究记录提示“{summary['summary']}”。你如何说明该记录与当前课题结论之间的证据关系？",
            RehearsalQuestionFocus.EVIDENCE,
            summary["id"] if isinstance(summary.get("id"), str) else None,
        )
        for summary in context.memory_view_summaries
        if isinstance(summary, dict)
        and str(summary.get("summary") or "").strip()
    ]


def _fallback_candidates(context: RehearsalContext) -> list[_QuestionCandidate]:
    topic = context.topic_name or "当前课题"
    return [
        _QuestionCandidate(
            f"请用一句话说明“{topic}”当前最核心的研究问题，以及你暂时不主张什么。",
            RehearsalQuestionFocus.SCOPE,
        ),
        _QuestionCandidate(
            "你当前最依赖的证据是什么？它是否来自同批、可对应且满足声明条件的样品？",
            RehearsalQuestionFocus.EVIDENCE,
        ),
        _QuestionCandidate(
            "下一步最小判别实验要固定哪些控制条件，并预先约定什么结果会推翻当前解释？",
            RehearsalQuestionFocus.EXPERIMENT,
        ),
    ]


def _personas(personas: list[RehearsalPersona]) -> list[RehearsalPersona]:
    if RehearsalPersona.MIXED in personas:
        return [
            RehearsalPersona.ADVISOR,
            RehearsalPersona.PEER,
            RehearsalPersona.COMMITTEE,
        ]
    return list(dict.fromkeys(personas)) or [RehearsalPersona.ADVISOR]


def _strict_prompt(prompt: str, intensity: RehearsalIntensity) -> str:
    if intensity is RehearsalIntensity.STRICT:
        return f"请给出可核查的条件、反例和判定顺序。{prompt}"
    if intensity is RehearsalIntensity.GENTLE:
        return f"请先说明你的思路，再回答：{prompt}"
    return prompt


def generate_questions(
    context: RehearsalContext,
    intensity: RehearsalIntensity,
    personas: list[RehearsalPersona],
    max_questions: int,
) -> list[RehearsalQuestion]:
    """从冻结上下文派生可复现的预演问题序列。"""
    candidates = _step_candidates(context) + _memory_candidates(context)
    candidates.extend(_fallback_candidates(context))
    selected = candidates[:max_questions]
    available_personas = _personas(personas)

    return [
        RehearsalQuestion(
            id=f"question-{index}",
            sequence=index,
            persona=available_personas[(index - 1) % len(available_personas)],
            prompt=_strict_prompt(candidate.prompt, intensity),
            source_refs=[candidate.source_ref] if candidate.source_ref else [],
            focus=candidate.focus,
        )
        for index, candidate in enumerate(selected, start=1)
    ]
