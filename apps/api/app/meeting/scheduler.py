"""Durable group meeting schedules and the API-process scheduler."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.storage.repositories import MeetingScheduleRepository
from app.storage.sqlite_store import SQLiteStore


class MeetingScheduleRequest(BaseModel):
    next_meeting_at: datetime

    @field_validator("next_meeting_at")
    @classmethod
    def normalize_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class MeetingScheduleResponse(BaseModel):
    group_chat_id: str
    next_meeting_at: datetime
    status: Literal["pending", "triggering", "triggered", "failed"]
    run_id: str | None = None
    error: str = ""
    triggered_at: float | None = None
    updated_at: float


def _response(record: dict) -> MeetingScheduleResponse:
    return MeetingScheduleResponse(
        group_chat_id=record["group_chat_id"],
        next_meeting_at=datetime.fromtimestamp(record["next_meeting_at"], tz=timezone.utc),
        status=record["status"],
        run_id=record.get("run_id"),
        error=record.get("error", ""),
        triggered_at=record.get("triggered_at"),
        updated_at=record["updated_at"],
    )


class MeetingScheduleService:
    def __init__(self, store: SQLiteStore | None = None) -> None:
        self.repository: MeetingScheduleRepository | None = (
            MeetingScheduleRepository(store) if store is not None else None
        )
        self._memory: dict[str, dict] = {}

    def configure_persistence(self, store: SQLiteStore | None) -> None:
        self.repository = MeetingScheduleRepository(store) if store is not None else None

    def save(self, group_chat_id: str, requested_at: datetime) -> MeetingScheduleResponse:
        timestamp = requested_at.timestamp()
        now = time.time()
        if self.repository is not None:
            self.repository.upsert(group_chat_id=group_chat_id, next_meeting_at=timestamp, now=now)
            return self.get(group_chat_id)
        self._memory[group_chat_id] = {
            "group_chat_id": group_chat_id,
            "next_meeting_at": timestamp,
            "status": "pending",
            "run_id": None,
            "error": "",
            "triggered_at": None,
            "updated_at": now,
        }
        return _response(self._memory[group_chat_id])

    def get(self, group_chat_id: str) -> MeetingScheduleResponse | None:
        record = self.repository.get(group_chat_id) if self.repository is not None else self._memory.get(group_chat_id)
        return None if record is None else _response(record)

    def delete_for_group(self, group_chat_id: str) -> None:
        if self.repository is not None:
            self.repository.delete_for_group(group_chat_id)
        self._memory.pop(group_chat_id, None)


class MeetingScheduler:
    """Poll due schedules and atomically claim each one before starting a run."""

    def __init__(
        self,
        repository: MeetingScheduleRepository,
        *,
        trigger: Callable[[str], str],
        clock: Callable[[], float] = time.time,
        poll_interval: float = 1.0,
    ) -> None:
        self.repository = repository
        self.trigger = trigger
        self.clock = clock
        self.poll_interval = max(poll_interval, 0.05)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_due_once(self) -> list[str]:
        run_ids: list[str] = []
        now = self.clock()
        for schedule in self.repository.list_due(now):
            group_chat_id = schedule["group_chat_id"]
            if not self.repository.claim(group_chat_id, now=now):
                continue
            try:
                run_id = self.trigger(group_chat_id)
            except Exception as exc:
                self.repository.mark_failed(group_chat_id, error=str(exc), now=self.clock())
                continue
            self.repository.mark_triggered(group_chat_id, run_id=run_id, now=self.clock())
            run_ids.append(run_id)
        return run_ids

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="forummind-meeting-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.poll_interval + 0.5, 1.0))
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_due_once()
            self._stop.wait(self.poll_interval)


schedule_service = MeetingScheduleService()
