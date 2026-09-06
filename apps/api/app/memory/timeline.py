"""进程内追加式 Memory 时间线：只追加、不覆盖、可回溯。"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from typing import Any

_seq = itertools.count(1)


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    kind: str
    payload: dict[str, Any]
    version: int
    supersedes: str | None
    created_at: float
    object_key: str | None = None
    data_space: str = "synthetic"


class MemoryTimeline:
    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def append(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        supersedes: str | None = None,
        object_key: str | None = None,
    ) -> MemoryEntry:
        """只追加；传 object_key 时按对象版本化，否则按 kind 版本化。"""
        version_count = sum(
            1
            for e in self._entries
            if e.kind == kind and (object_key is None or e.object_key == object_key)
        )
        entry = MemoryEntry(
            id=f"mem-{next(_seq)}",
            kind=kind,
            payload=payload,
            version=version_count + 1,
            supersedes=supersedes,
            created_at=time.time(),
            object_key=object_key,
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> list[MemoryEntry]:
        """按追加顺序返回全部 entry 的快照。"""
        return list(self._entries)

    def latest(self, kind: str, *, object_key: str | None = None) -> MemoryEntry | None:
        """返回该 kind 或该对象最新一条；无则 None。"""
        found = [
            e
            for e in self._entries
            if e.kind == kind and (object_key is None or e.object_key == object_key)
        ]
        return found[-1] if found else None
