"""Process-local append-only tool call audit storage."""
from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from app.tools.schemas import ToolCallRecord


class AuditRecorder:
    def __init__(self, sink: Callable[[ToolCallRecord], object] | None = None) -> None:
        self._records: list[ToolCallRecord] = []
        self._sink = sink
        self._lock = RLock()

    def append(self, record: ToolCallRecord) -> ToolCallRecord:
        stored = record.model_copy(deep=True)
        with self._lock:
            self._records.append(stored)
        if self._sink is not None:
            self._sink(stored.model_copy(deep=True))
        return stored.model_copy(deep=True)

    def list_for_run(self, run_id: str) -> list[ToolCallRecord]:
        with self._lock:
            return [record.model_copy(deep=True) for record in self._records if record.run_id == run_id]

    def reset(self, run_id: str | None = None) -> None:
        with self._lock:
            if run_id is None:
                self._records.clear()
            else:
                self._records = [record for record in self._records if record.run_id != run_id]
