"""Candidate Streaming Buffer（design.md §2.6、§8.6，tasks.md Task 21）。

Pi/live runtime 的 streaming 输出先进入未校验候选缓冲区：

- `append_event`：只接受初始状态 `streaming` / `completed`。
- `mark_validated` / `mark_rejected`：只有显式调用才可改变状态。
- `list_events` / `reset_buffer`：按 run 读取 / 清空。

边界约定：

- 未校验内容不能成为正式群聊消息、正式产物或正式 Memory。
- buffer 不写 `MemoryTimeline`，不访问文件系统 / 数据库 / LLM。
"""

from __future__ import annotations

from app.agent_runtime.schemas import CandidateStreamEvent

_INITIAL_STATUSES = {"streaming", "completed"}

_buffer: dict[str, list[CandidateStreamEvent]] = {}


class CandidateEventNotFoundError(KeyError):
    """按 event id 找不到候选事件。"""


def append_event(event: CandidateStreamEvent) -> CandidateStreamEvent:
    """追加一个未校验候选事件；初始状态只允许 streaming / completed。"""
    if event.status not in _INITIAL_STATUSES:
        raise ValueError(
            f"候选事件初始状态必须是 streaming 或 completed，当前 {event.status!r}"
        )
    _buffer.setdefault(event.run_id, []).append(event)
    return event


def list_events(run_id: str) -> list[CandidateStreamEvent]:
    """按追加顺序返回该 run 的候选事件；无事件时返回空列表。"""
    return list(_buffer.get(run_id, []))


def _set_status(event_id: str, status: str) -> CandidateStreamEvent:
    """把事件状态更新为 validated / rejected（显式操作才可调用）。"""
    for events in _buffer.values():
        for index, event in enumerate(events):
            if event.id == event_id:
                updated = event.model_copy(update={"status": status})
                events[index] = updated
                return updated
    raise CandidateEventNotFoundError(f"候选事件不存在: {event_id}")


def mark_validated(event_id: str) -> CandidateStreamEvent:
    """显式标记事件为 validated（通过 ForumMind 校验门后）。"""
    return _set_status(event_id, "validated")


def mark_rejected(event_id: str) -> CandidateStreamEvent:
    """显式标记事件为 rejected（未通过校验，记录原因由调用方写入 warnings）。"""
    return _set_status(event_id, "rejected")


def reset_buffer() -> None:
    """清空全部候选事件（demo reset / 测试用）。"""
    _buffer.clear()
