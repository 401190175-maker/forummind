"""SQLite store and repository contract tests."""

import sqlite3
import threading

import pytest

from app.storage.repositories import (
    AgentRepository,
    GroupChatRepository,
    MeetingRepository,
    MessageRepository,
    RunRepository,
)
from app.storage.sqlite_store import SQLiteStore


def test_agent_repository_reopens_agent_and_test_result(tmp_path):
    path = tmp_path / "forummind.db"
    first = SQLiteStore(path)
    first.initialize()
    repository = AgentRepository(first)
    repository.create(
        {"agent_id": "agent-custom", "name": "自定义 Agent", "role": "master_student"},
        enabled=False,
        created_at=1.0,
        updated_at=1.0,
    )
    repository.save_test_result(
        {
            "test_id": "agent-test-1",
            "agent_id": "agent-custom",
            "status": "failed",
            "runtime": "pi",
            "result": "",
            "error": "Pi timeout",
            "duration_ms": 12,
            "created_at": 2.0,
        }
    )
    first.close()

    second = SQLiteStore(path)
    second.initialize()
    recovered = AgentRepository(second).get("agent-custom")
    assert recovered["profile"]["agent_id"] == "agent-custom"
    assert recovered["enabled"] is False
    assert AgentRepository(second).get_test_result("agent-test-1")["status"] == "failed"
    second.close()


def test_agent_repository_duplicate_id_is_rejected(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    repository = AgentRepository(store)
    record = {"agent_id": "agent-1", "name": "Agent", "role": "master_student"}
    repository.create(record, enabled=True, created_at=1.0, updated_at=1.0)
    with pytest.raises(sqlite3.IntegrityError):
        repository.create(record, enabled=True, created_at=2.0, updated_at=2.0)
    store.close()


def test_store_reopens_group_chat_and_run(tmp_path):
    path = tmp_path / "forummind.db"
    first = SQLiteStore(path)
    first.initialize()
    GroupChatRepository(first).save(
        {
            "group_chat_id": "gc-1",
            "data_space": "synthetic",
            "payload": {"group_chat": {"id": "gc-1"}},
            "created_at": 1.0,
            "updated_at": 1.0,
        }
    )
    RunRepository(first).save_snapshot(
        {
            "run_id": "run-1",
            "group_chat_id": "gc-1",
            "status": "running",
            "mode": "replay",
            "phase": "meeting",
            "cycle": 1,
            "snapshot": {"run_id": "run-1", "steps": []},
            "created_at": 1.0,
            "updated_at": 1.0,
        }
    )
    first.close()

    second = SQLiteStore(path)
    second.initialize()
    assert (
        GroupChatRepository(second).get("gc-1")["payload"]["group_chat"]["id"]
        == "gc-1"
    )
    assert (
        RunRepository(second).get_snapshot("run-1")["snapshot"]["run_id"]
        == "run-1"
    )
    second.close()


def test_initialize_is_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    store.initialize()
    tables = {
        row[0]
        for row in store.connection().execute(
            "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
        )
    }
    assert {"group_chats", "messages", "runs", "meeting_events"} <= tables
    store.close()


def test_initialize_migrates_legacy_research_tasks_before_creating_index(tmp_path):
    path = tmp_path / "legacy-research-tasks.db"
    legacy = sqlite3.connect(path)
    legacy.execute(
        """
        CREATE TABLE research_tasks (
            task_id TEXT PRIMARY KEY,
            group_chat_id TEXT NOT NULL,
            title TEXT NOT NULL,
            question TEXT NOT NULL,
            data_space TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    legacy.commit()
    legacy.close()

    store = SQLiteStore(path)
    store.initialize()

    columns = {
        row["name"]
        for row in store.connection().execute("PRAGMA table_info(research_tasks)")
    }
    indexes = {
        row["name"]
        for row in store.connection().execute("PRAGMA index_list(research_tasks)")
    }
    assert "source_clarification_id" in columns
    assert "research_tasks_group_clarification" in indexes
    store.close()


def test_message_and_run_are_scoped_by_group_chat(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    messages = MessageRepository(store)
    messages.append(
        {
            "message_id": "msg-1",
            "group_chat_id": "gc-1",
            "sender_type": "user",
            "content": "a'; DROP TABLE messages; --",
            "mention": None,
            "data_space": "synthetic",
            "created_at": 1.0,
        }
    )
    assert messages.list("gc-1")[0]["content"].startswith("a'")
    assert messages.list("gc-unknown") == []
    assert RunRepository(store).get_snapshot("run-unknown") is None
    assert messages.list("gc-1")[0]["content"] == "a'; DROP TABLE messages; --"
    store.close()


def test_failed_transaction_leaves_no_partial_run_or_event(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs
                    (run_id, group_chat_id, task_id, status, mode, phase, cycle,
                     snapshot_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run-1",
                    "gc-1",
                    "",
                    "running",
                    "replay",
                    "meeting",
                    1,
                    "{}",
                    1.0,
                    1.0,
                ),
            )
            connection.execute(
                """
                INSERT INTO runs
                    (run_id, group_chat_id, task_id, status, mode, phase, cycle,
                     snapshot_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run-1",
                    "gc-1",
                    "",
                    "running",
                    "replay",
                    "meeting",
                    1,
                    "{}",
                    1.0,
                    1.0,
                ),
            )
    assert RunRepository(store).get_snapshot("run-1") is None

    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO meeting_events
                    (event_id, run_id, actor_id, actor_role, kind,
                     content, timestamp, source_refs_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("event-1", "run-1", "pi", "pi", "message", "x", 1.0, "[]"),
            )
            connection.execute(
                """
                INSERT INTO meeting_events
                    (event_id, run_id, actor_id, actor_role, kind,
                     content, timestamp, source_refs_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("event-1", "run-1", "pi", "pi", "message", "y", 2.0, "[]"),
            )
    assert MeetingRepository(store).list_events("run-1") == []
    store.close()


def test_meeting_events_are_ordered_by_timestamp_and_id(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    repository = MeetingRepository(store)
    repository.append_event(
        {
            "event_id": "event-b",
            "run_id": "run-1",
            "actor_id": "agent-1",
            "actor_role": "master_student",
            "kind": "message",
            "content": "later",
            "timestamp": 2.0,
            "source_refs": [],
        }
    )
    repository.append_event(
        {
            "event_id": "event-a",
            "run_id": "run-1",
            "actor_id": "agent-2",
            "actor_role": "master_student",
            "kind": "message",
            "content": "earlier",
            "timestamp": 1.0,
            "source_refs": [],
        }
    )
    assert [event["event_id"] for event in repository.list_events("run-1")] == [
        "event-a",
        "event-b",
    ]
    store.close()


def test_store_serializes_transactions_across_threads(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    entered = threading.Event()
    release = threading.Event()
    writer_done = threading.Event()

    def hold_transaction():
        with store.transaction() as connection:
            connection.execute("SELECT 1")
            entered.set()
            release.wait(timeout=2)

    def write_snapshot():
        entered.wait(timeout=2)
        RunRepository(store).save_snapshot(
            {
                "run_id": "run-thread",
                "group_chat_id": "gc-1",
                "status": "running",
                "mode": "replay",
                "phase": "meeting",
                "cycle": 1,
                "snapshot": {"run_id": "run-thread"},
                "created_at": 1.0,
                "updated_at": 1.0,
            }
        )
        writer_done.set()

    holder = threading.Thread(target=hold_transaction)
    writer = threading.Thread(target=write_snapshot)
    holder.start()
    assert entered.wait(timeout=2)
    writer.start()

    assert not writer_done.wait(timeout=0.1)
    release.set()
    holder.join(timeout=2)
    writer.join(timeout=2)

    assert writer_done.is_set()
    assert RunRepository(store).get_snapshot("run-thread") is not None
    store.close()
