"""实验视图投影：从 raw steps 与 append-only Memory 派生只读 UI 数据。"""
from __future__ import annotations

from typing import Any

from app.memory.timeline import MemoryEntry

BOUNDARY_NOTES = [
    "synthetic demo 数据不是真实实验结果。",
    "AI 不执行真实实验，只记录和展示演示实验设计与结果。",
    "符合预测不等于证明因果，支持程度变化仍需独立验证。",
    "后验解释必须标记为后验，不能倒写为预注册结论。",
    "Pi state / live runtime 输出不等于正式 Research Memory。",
]


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, MemoryEntry):
        return value.payload if isinstance(value.payload, dict) else {}
    if hasattr(value, "payload"):
        raw = getattr(value, "payload")
        return raw if isinstance(raw, dict) else {}
    if isinstance(value, dict):
        raw = value.get("payload", value)
        return raw if isinstance(raw, dict) else {}
    return {}


def _str(value: Any, fallback: str = "—") -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _step_fields(step: Any) -> tuple[str, str]:
    if isinstance(step, dict):
        return _str(step.get("phase"), ""), _str(step.get("kind"), "")
    return _str(getattr(step, "phase", ""), ""), _str(getattr(step, "kind", ""), "")


def _step_timestamp(step: Any) -> float | None:
    if isinstance(step, dict):
        value = step.get("timestamp")
    else:
        value = getattr(step, "timestamp", None)
    return value if isinstance(value, int | float) else None


def _latest_entry(entries: list[Any], kind: str) -> Any | None:
    for entry in reversed(entries):
        if getattr(entry, "kind", None) == kind:
            return entry
        if isinstance(entry, dict) and entry.get("kind") == kind:
            return entry
    return None


def _entry_id(entry: Any) -> str | None:
    if isinstance(entry, dict):
        value = entry.get("id")
    else:
        value = getattr(entry, "id", None)
    return value if isinstance(value, str) else None


def _entry_supersedes(entry: Any) -> str | None:
    if isinstance(entry, dict):
        value = entry.get("supersedes")
    else:
        value = getattr(entry, "supersedes", None)
    return value if isinstance(value, str) else None


def _approval_boundary(steps: list[Any], plan_payload: dict[str, Any]) -> dict[str, str] | None:
    option = plan_payload.get("approval_option")
    reason = plan_payload.get("approval_reason")
    if isinstance(option, str) and isinstance(reason, str):
        return {"option": option, "reason": reason}
    for step in reversed(steps):
        phase, kind = _step_fields(step)
        if phase != "meeting" or kind != "decision":
            continue
        payload = _payload(step)
        step_option = payload.get("option")
        step_reason = payload.get("reason")
        if isinstance(step_option, str) and isinstance(step_reason, str):
            return {"option": step_option, "reason": step_reason}
    return None


def _plan_view(steps: list[Any], entries: list[Any]) -> dict[str, Any] | None:
    plan_entry = _latest_entry(entries, "ExperimentPlan")
    if plan_entry is None:
        return None
    payload = _payload(plan_entry)
    return {
        "title": "最小判别实验方案",
        "candidate_explanations": _list(payload.get("candidate_explanations")),
        "controls": _list(payload.get("controls")),
        "sample_chain": _str(payload.get("sample_chain")),
        "measurements": _list(payload.get("measurements")),
        "branches": _list(payload.get("branches")),
        "branch_effects": _list(payload.get("branch_effects")),
        "cost_risk": _str(payload.get("cost_risk")),
        "approval_boundary": _approval_boundary(steps, payload),
    }


def _results_view(steps: list[Any], entries: list[Any]) -> dict[str, Any] | None:
    result_entry = _latest_entry(entries, "ExperimentResult")
    if result_entry is None:
        return None
    payload = _payload(result_entry)
    imported_at = None
    for step in reversed(steps):
        phase, kind = _step_fields(step)
        if phase == "data_import" and kind == "results":
            imported_at = _step_timestamp(step)
            break
    return {
        "source": _str(payload.get("source")),
        "rows": _list(payload.get("rows")),
        "notes": _str(payload.get("notes")),
        "validation_summary": _str(payload.get("validation_summary")),
        "imported_at": imported_at,
    }


def _hypothesis_updates(entries: list[Any]) -> list[dict[str, str]]:
    updates: list[dict[str, str]] = []
    for entry in entries:
        kind = entry.get("kind") if isinstance(entry, dict) else getattr(entry, "kind", None)
        if kind != "HypothesisUpdate":
            continue
        payload = _payload(entry)
        status = payload.get("status")
        updates.append({
            "claim_id": _str(payload.get("claim_id")),
            "status": status if status in {"supported", "weakened", "inconclusive", "posterior"} else "inconclusive",
            "reason": _str(payload.get("reason")),
            "causal_boundary": _str(
                payload.get("causal_boundary"),
                "支持程度变化不等于因果证明",
            ),
        })
    return updates


def _research_state_change(entries: list[Any]) -> dict[str, Any] | None:
    states = [
        entry
        for entry in entries
        if (entry.get("kind") if isinstance(entry, dict) else getattr(entry, "kind", None)) == "ResearchState"
    ]
    if not states:
        return None
    current = states[-1]
    current_payload = _payload(current)
    previous_ref = _entry_supersedes(current)
    return {
        "previous_ref": previous_ref,
        "current_ref": _entry_id(current),
        "summary": _str(current_payload.get("summary")),
        "trigger": _str(current_payload.get("trigger")),
        "supersedes": previous_ref is not None,
        "preserves_old_version": True,
    }


def build_experiment_view(*, phase: str, steps: list[Any], entries: list[Any]) -> dict[str, Any]:
    """构造 RunSnapshot 上的 `experiment_view`，不修改输入。"""
    return {
        "data_space": "synthetic",
        "phase": phase,
        "plan": _plan_view(steps, entries),
        "results": _results_view(steps, entries),
        "hypothesis_updates": _hypothesis_updates(entries),
        "research_state_change": _research_state_change(entries)
        if _latest_entry(entries, "ExperimentResult") is not None
        else None,
        "boundary_notes": list(BOUNDARY_NOTES),
    }
