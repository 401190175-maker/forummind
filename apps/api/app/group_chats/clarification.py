"""Pure clarification limits and completion rules."""

from __future__ import annotations

from app.group_chats.schemas import ClarificationTurn

MAX_QUESTIONS = 7

_CATEGORY_MARKERS: dict[str, tuple[str, ...]] = {
    "goal": ("决策", "目标", "支持", "选择", "判断", "决定"),
    "phenomenon": ("现象", "强度", "孔", "数据", "指标", "样品", "机制"),
    "constraints": ("约束", "条件", "控制", "设备", "周期", "成本", "安全", "湿密度"),
    "deliverable": ("交付", "观点卡", "实验建议", "组会", "报告", "验收", "文献整理"),
}


def clarification_is_ready(initial_intent: str, turns: list[ClarificationTurn]) -> bool:
    """Allow early completion when three task-context categories are explicit."""
    text = " ".join([initial_intent, *(turn.answer or "" for turn in turns)])
    matched = sum(
        any(marker in text for marker in markers)
        for markers in _CATEGORY_MARKERS.values()
    )
    return matched >= 3
