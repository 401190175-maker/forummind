"""Server-backed meeting schedule and one-shot trigger tests."""

import importlib

from fastapi.testclient import TestClient

from app.main import app
from app.storage.sqlite_store import SQLiteStore


def test_due_schedule_is_claimed_and_triggered_only_once(tmp_path):
    module = importlib.import_module("app.meeting.scheduler")
    assert hasattr(module, "MeetingScheduler")
    repository_type = getattr(
        importlib.import_module("app.storage.repositories"),
        "MeetingScheduleRepository",
        None,
    )
    assert repository_type is not None
    MeetingScheduler = module.MeetingScheduler
    MeetingScheduleRepository = repository_type
    store = SQLiteStore(tmp_path / "schedule.db")
    store.initialize()
    repository = MeetingScheduleRepository(store)
    triggered = []
    scheduler = MeetingScheduler(
        repository,
        trigger=lambda group_chat_id: triggered.append(group_chat_id) or "run-1",
        clock=lambda: 100.0,
    )
    repository.upsert(
        group_chat_id="gc-1",
        next_meeting_at=99.0,
        now=90.0,
    )

    assert scheduler.run_due_once() == ["run-1"]
    assert scheduler.run_due_once() == []
    assert triggered == ["gc-1"]
    schedule = repository.get("gc-1")
    assert schedule["status"] == "triggered"
    assert schedule["run_id"] == "run-1"
    store.close()


def test_future_schedule_is_not_triggered(tmp_path):
    module = importlib.import_module("app.meeting.scheduler")
    assert hasattr(module, "MeetingScheduler")
    repository_type = getattr(
        importlib.import_module("app.storage.repositories"),
        "MeetingScheduleRepository",
        None,
    )
    assert repository_type is not None
    MeetingScheduler = module.MeetingScheduler
    MeetingScheduleRepository = repository_type
    store = SQLiteStore(tmp_path / "schedule.db")
    store.initialize()
    repository = MeetingScheduleRepository(store)
    scheduler = MeetingScheduler(
        repository,
        trigger=lambda group_chat_id: "run-never",
        clock=lambda: 100.0,
    )
    repository.upsert(group_chat_id="gc-1", next_meeting_at=101.0, now=90.0)

    assert scheduler.run_due_once() == []
    assert repository.get("gc-1")["status"] == "pending"
    store.close()


def test_schedule_api_persists_the_next_meeting_for_a_group():
    client = TestClient(app)
    response = client.post(
        "/group-chats",
        json={
            "topic_name": "schedule-api-test",
            "topic_summary": "schedule-api-test",
            "member_selection": {
                "postdoc": {"selection_mode": "existing", "agent_ids": ["agent-postdoc-1"]},
                "phd_student": {"selection_mode": "existing", "agent_ids": ["agent-phd-1"]},
                "master_student": {"selection_mode": "existing", "agent_ids": [
                    "agent-ms-1", "agent-ms-2", "agent-ms-3"
                ]},
            },
        },
    )
    assert response.status_code == 200
    group_chat_id = response.json()["group_chat"]["id"]
    try:
        saved = client.put(
            f"/group-chats/{group_chat_id}/meeting-schedule",
            json={"next_meeting_at": "2030-01-02T03:04:05Z"},
        )
        assert saved.status_code == 200
        assert saved.json()["status"] == "pending"
        assert saved.json()["next_meeting_at"].startswith("2030-01-02T03:04:05")
        assert client.get(f"/group-chats/{group_chat_id}/meeting-schedule").json() == saved.json()
    finally:
        client.delete(f"/group-chats/{group_chat_id}")
