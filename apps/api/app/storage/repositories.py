"""Parameterized repositories for the minimal SQLite persistence layer."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from app.storage.sqlite_store import SQLiteStore


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(value: str) -> Any:
    return json.loads(value)


def _write(store: SQLiteStore, operation: Callable[[Any], None]) -> None:
    if store.in_transaction:
        operation(store.connection())
    else:
        with store.transaction() as connection:
            operation(connection)


def _save_cursor(store: SQLiteStore, run_id: str, cursor: int) -> int:
    if cursor < 0:
        raise ValueError("cursor must be non-negative")
    now = time.time()

    def operation(connection) -> int:
        connection.execute(
            """
            INSERT INTO runtime_cursors(run_id, cursor, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                cursor = MAX(runtime_cursors.cursor, excluded.cursor),
                updated_at = excluded.updated_at
            """,
            (run_id, cursor, now),
        )
        row = connection.execute(
            "SELECT cursor FROM runtime_cursors WHERE run_id = ?", (run_id,)
        ).fetchone()
        return int(row["cursor"])

    if store.in_transaction:
        return operation(store.connection())
    with store.transaction() as connection:
        return operation(connection)


def _get_cursor(store: SQLiteStore, run_id: str) -> int:
    with store.locked() as connection:
        row = connection.execute(
            "SELECT cursor FROM runtime_cursors WHERE run_id = ?", (run_id,)
        ).fetchone()
    return int(row["cursor"]) if row is not None else 0


class AgentRepository:
    """Persist Agent profiles, lifecycle metadata, and test results."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create(
        self,
        profile: dict,
        *,
        enabled: bool,
        created_at: float,
        updated_at: float,
    ) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO agents
                    (agent_id, profile_json, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    profile["agent_id"],
                    _encode(profile),
                    int(enabled),
                    created_at,
                    updated_at,
                ),
            )

        _write(self.store, operation)

    def get(self, agent_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT agent_id, profile_json, enabled, created_at, updated_at
                FROM agents WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "agent_id": row["agent_id"],
            "profile": _decode(row["profile_json"]),
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT agent_id, profile_json, enabled, created_at, updated_at
                FROM agents ORDER BY created_at, agent_id
                """
            ).fetchall()
        return [
            {
                "agent_id": row["agent_id"],
                "profile": _decode(row["profile_json"]),
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def update(
        self,
        agent_id: str,
        profile: dict,
        *,
        enabled: bool,
        updated_at: float,
    ) -> None:
        def operation(connection) -> None:
            cursor = connection.execute(
                """
                UPDATE agents
                SET profile_json = ?, enabled = ?, updated_at = ?
                WHERE agent_id = ?
                """,
                (_encode(profile), int(enabled), updated_at, agent_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(agent_id)

        _write(self.store, operation)

    def save_test_result(self, result: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO agent_test_results
                    (test_id, agent_id, status, runtime, result_json,
                     duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["test_id"],
                    result["agent_id"],
                    result["status"],
                    result["runtime"],
                    _encode(
                        {
                            "result": result.get("result", ""),
                            "error": result.get("error", ""),
                        }
                    ),
                    result["duration_ms"],
                    result["created_at"],
                ),
            )

        _write(self.store, operation)

    def get_test_result(self, test_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT test_id, agent_id, status, runtime, result_json,
                       duration_ms, created_at
                FROM agent_test_results WHERE test_id = ?
                """,
                (test_id,),
            ).fetchone()
        return None if row is None else self._test_result_from_row(row)

    def get_latest_test_result(self, agent_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT test_id, agent_id, status, runtime, result_json,
                       duration_ms, created_at
                FROM agent_test_results
                WHERE agent_id = ?
                ORDER BY created_at DESC, test_id DESC
                LIMIT 1
                """,
                (agent_id,),
            ).fetchone()
        return None if row is None else self._test_result_from_row(row)

    @staticmethod
    def _test_result_from_row(row: Any) -> dict:
        payload = _decode(row["result_json"])
        return {
            "test_id": row["test_id"],
            "agent_id": row["agent_id"],
            "status": row["status"],
            "runtime": row["runtime"],
            "result": payload.get("result", ""),
            "error": payload.get("error", ""),
            "duration_ms": row["duration_ms"],
            "created_at": row["created_at"],
        }

    def delete_all(self) -> None:
        def operation(connection) -> None:
            connection.execute("DELETE FROM agent_test_results")
            connection.execute("DELETE FROM agents")

        _write(self.store, operation)


class GroupChatRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, record: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO group_chats
                    (group_chat_id, data_space, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(group_chat_id) DO UPDATE SET
                    data_space = excluded.data_space,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record["group_chat_id"],
                    record.get("data_space", "synthetic"),
                    _encode(record["payload"]),
                    record["created_at"],
                    record["updated_at"],
                ),
            )

        _write(self.store, operation)

    def get(self, group_chat_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT group_chat_id, data_space, payload_json, created_at, updated_at
                FROM group_chats WHERE group_chat_id = ?
                """,
                (group_chat_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "group_chat_id": row["group_chat_id"],
            "data_space": row["data_space"],
            "payload": _decode(row["payload_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT group_chat_id, data_space, payload_json, created_at, updated_at
                FROM group_chats ORDER BY created_at, group_chat_id
                """
            ).fetchall()
        return [
            {
                "group_chat_id": row["group_chat_id"],
                "data_space": row["data_space"],
                "payload": _decode(row["payload_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def delete(self, group_chat_id: str) -> bool:
        def operation(connection) -> bool:
            cursor = connection.execute(
                "DELETE FROM group_chats WHERE group_chat_id = ?",
                (group_chat_id,),
            )
            return cursor.rowcount > 0

        if self.store.in_transaction:
            return operation(self.store.connection())
        with self.store.transaction() as connection:
            return operation(connection)

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM group_chats"))


class MessageRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def append(self, record: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO messages
                    (message_id, group_chat_id, sender_type, sender_id, content,
                     mention_json, task_id, attachment_ids_json, message_kind,
                     payload_json, reply_to_message_id, data_space, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["message_id"],
                    record["group_chat_id"],
                    record["sender_type"],
                    record.get("sender_id"),
                    record["content"],
                    None if record.get("mention") is None else _encode(record["mention"]),
                    record.get("task_id"),
                    _encode(record.get("attachment_ids", [])),
                    record.get("kind", "text"),
                    _encode(record.get("payload", {})),
                    record.get("reply_to_message_id"),
                    record.get("data_space", "synthetic"),
                    record["created_at"],
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO messages_fts(message_id, group_chat_id, content) VALUES (?, ?, ?)",
                (record["message_id"], record["group_chat_id"], record["content"]),
            )

        _write(self.store, operation)

    def list(self, group_chat_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT message_id, group_chat_id, sender_type, content,
                       sender_id, mention_json, task_id, attachment_ids_json,
                       message_kind, payload_json, reply_to_message_id,
                       data_space, created_at
                FROM messages
                WHERE group_chat_id = ?
                ORDER BY created_at, message_id
                """,
                (group_chat_id,),
            ).fetchall()
        return [
            {
                "message_id": row["message_id"],
                "group_chat_id": row["group_chat_id"],
                "sender_type": row["sender_type"],
                "sender_id": row["sender_id"],
                "content": row["content"],
                "mention": (
                    None
                    if row["mention_json"] is None
                    else _decode(row["mention_json"])
                ),
                "task_id": row["task_id"],
                "attachment_ids": _decode(row["attachment_ids_json"] or "[]"),
                "kind": row["message_kind"],
                "payload": _decode(row["payload_json"] or "{}"),
                "reply_to_message_id": row["reply_to_message_id"],
                "data_space": row["data_space"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete_for_group(self, group_chat_id: str) -> None:
        def operation(connection) -> None:
            connection.execute("DELETE FROM messages WHERE group_chat_id = ?", (group_chat_id,))
            connection.execute("DELETE FROM messages_fts WHERE group_chat_id = ?", (group_chat_id,))

        _write(self.store, operation)

    def delete_all(self) -> None:
        def operation(connection) -> None:
            connection.execute("DELETE FROM messages")
            connection.execute("DELETE FROM messages_fts")

        _write(self.store, operation)


class MeetingScheduleRepository:
    """Persist one pending or completed meeting schedule per group."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def upsert(self, *, group_chat_id: str, next_meeting_at: float, now: float) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                """
                INSERT INTO meeting_schedules
                    (group_chat_id, next_meeting_at, status, run_id, error,
                     triggered_at, created_at, updated_at)
                VALUES (?, ?, 'pending', NULL, '', NULL, ?, ?)
                ON CONFLICT(group_chat_id) DO UPDATE SET
                    next_meeting_at = excluded.next_meeting_at,
                    status = 'pending', run_id = NULL, error = '',
                    triggered_at = NULL, updated_at = excluded.updated_at
                """,
                (group_chat_id, next_meeting_at, now, now),
            ),
        )

    def get(self, group_chat_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT * FROM meeting_schedules WHERE group_chat_id = ?",
                (group_chat_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def list_due(self, now: float) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT * FROM meeting_schedules
                WHERE status = 'pending' AND next_meeting_at <= ?
                ORDER BY next_meeting_at, group_chat_id
                """,
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim(self, group_chat_id: str, *, now: float) -> bool:
        def operation(connection) -> bool:
            cursor = connection.execute(
                """
                UPDATE meeting_schedules
                SET status = 'triggering', updated_at = ?
                WHERE group_chat_id = ? AND status = 'pending' AND next_meeting_at <= ?
                """,
                (now, group_chat_id, now),
            )
            return cursor.rowcount == 1

        if self.store.in_transaction:
            return operation(self.store.connection())
        with self.store.transaction() as connection:
            return operation(connection)

    def mark_triggered(self, group_chat_id: str, *, run_id: str, now: float) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                """
                UPDATE meeting_schedules
                SET status = 'triggered', run_id = ?, triggered_at = ?, updated_at = ?
                WHERE group_chat_id = ? AND status = 'triggering'
                """,
                (run_id, now, now, group_chat_id),
            ),
        )

    def mark_failed(self, group_chat_id: str, *, error: str, now: float) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                """
                UPDATE meeting_schedules
                SET status = 'failed', error = ?, triggered_at = ?, updated_at = ?
                WHERE group_chat_id = ? AND status = 'triggering'
                """,
                (error, now, now, group_chat_id),
            ),
        )

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                "DELETE FROM meeting_schedules WHERE group_chat_id = ?",
                (group_chat_id,),
            ),
        )

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM meeting_schedules"))


class ClarificationRepository:
    """Persist the server-owned clarification conversation and its state."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create(self, record: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO clarifications
                    (clarification_id, group_chat_id, mention_json,
                    clarifier_agent_id, initial_intent, turns_json, status,
                     question_id, question, question_number, max_questions, dataset_refs_json,
                     error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["clarification_id"],
                    record["group_chat_id"],
                    _encode(record["mention"]),
                    record["clarifier_agent_id"],
                    record["initial_intent"],
                    _encode(record.get("turns", [])),
                    record["status"],
                    record.get("question_id"),
                    record.get("question"),
                    record["question_number"],
                    record.get("max_questions", 7),
                    _encode(record.get("dataset_refs", [])),
                    record.get("error", ""),
                    record["created_at"],
                    record["updated_at"],
                ),
            )

        _write(self.store, operation)

    def get(self, clarification_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT clarification_id, group_chat_id, mention_json,
                       clarifier_agent_id, initial_intent, turns_json, status,
                       question_id, question, question_number, max_questions, dataset_refs_json,
                       error, created_at, updated_at
                FROM clarifications WHERE clarification_id = ?
                """,
                (clarification_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def update(self, clarification_id: str, record: dict) -> None:
        def operation(connection) -> None:
            cursor = connection.execute(
                """
                UPDATE clarifications
                SET turns_json = ?, status = ?, question_id = ?, question = ?,
                    question_number = ?, max_questions = ?, dataset_refs_json = ?, error = ?,
                    updated_at = ?
                WHERE clarification_id = ?
                """,
                (
                    _encode(record.get("turns", [])),
                    record["status"],
                    record.get("question_id"),
                    record.get("question"),
                    record["question_number"],
                    record.get("max_questions", 7),
                    _encode(record.get("dataset_refs", [])),
                    record.get("error", ""),
                    record["updated_at"],
                    clarification_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(clarification_id)

        _write(self.store, operation)

    def list_for_group(self, group_chat_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT clarification_id, group_chat_id, mention_json,
                       clarifier_agent_id, initial_intent, turns_json, status,
                       question_id, question, question_number, max_questions, dataset_refs_json,
                       error, created_at, updated_at
                FROM clarifications
                WHERE group_chat_id = ?
                ORDER BY created_at, clarification_id
                """,
                (group_chat_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                "DELETE FROM clarifications WHERE group_chat_id = ?",
                (group_chat_id,),
            ),
        )

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM clarifications"))

    @staticmethod
    def _from_row(row: Any) -> dict:
        return {
            "clarification_id": row["clarification_id"],
            "group_chat_id": row["group_chat_id"],
            "mention": _decode(row["mention_json"]),
            "clarifier_agent_id": row["clarifier_agent_id"],
            "initial_intent": row["initial_intent"],
            "turns": _decode(row["turns_json"]),
            "status": row["status"],
            "question_id": row["question_id"],
            "question": row["question"],
            "question_number": row["question_number"],
            "max_questions": row["max_questions"],
            "dataset_refs": _decode(row["dataset_refs_json"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class FormalTaskRepository:
    """Persist confirmed task context independently from clarification turns."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, context: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO formal_tasks
                    (clarification_id, group_chat_id, context_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(clarification_id) DO UPDATE SET
                    group_chat_id = excluded.group_chat_id,
                    context_json = excluded.context_json
                """,
                (
                    context["clarification_id"],
                    context["group_chat_id"],
                    _encode(context),
                    context["confirmed_at"],
                ),
            )

        _write(self.store, operation)

    def get(self, clarification_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT context_json FROM formal_tasks WHERE clarification_id = ?",
                (clarification_id,),
            ).fetchone()
        return None if row is None else _decode(row["context_json"])

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                "DELETE FROM formal_tasks WHERE group_chat_id = ?",
                (group_chat_id,),
            ),
        )

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM formal_tasks"))


class ArtifactRepository:
    """Persist generated Markdown research artifacts and their provenance."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, artifact: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO artifacts
                    (artifact_id, run_id, group_chat_id, agent_id,
                     artifact_type, filename, content, data_space,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    content = excluded.content,
                    filename = excluded.filename,
                    updated_at = excluded.updated_at
                """,
                (
                    artifact["artifact_id"],
                    artifact["run_id"],
                    artifact["group_chat_id"],
                    artifact["agent_id"],
                    artifact["artifact_type"],
                    artifact["filename"],
                    artifact["content"],
                    artifact.get("data_space", "synthetic"),
                    artifact["created_at"],
                    artifact["updated_at"],
                ),
            )

        _write(self.store, operation)

    def list_for_run(self, run_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, run_id, group_chat_id, agent_id,
                       artifact_type, filename, content, data_space,
                       created_at, updated_at
                FROM artifacts
                WHERE run_id = ?
                ORDER BY created_at, artifact_id
                """,
                (run_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, artifact_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT artifact_id, run_id, group_chat_id, agent_id,
                       artifact_type, filename, content, data_space,
                       created_at, updated_at
                FROM artifacts WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                "DELETE FROM artifacts WHERE group_chat_id = ?",
                (group_chat_id,),
            ),
        )

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM artifacts"))

    @staticmethod
    def _from_row(row: Any) -> dict:
        return {
            "artifact_id": row["artifact_id"],
            "run_id": row["run_id"],
            "group_chat_id": row["group_chat_id"],
            "agent_id": row["agent_id"],
            "artifact_type": row["artifact_type"],
            "filename": row["filename"],
            "content": row["content"],
            "data_space": row["data_space"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class RunRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save_snapshot(self, snapshot: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO runs
                    (run_id, group_chat_id, task_id, status, mode, phase, cycle,
                     snapshot_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    group_chat_id = excluded.group_chat_id,
                    task_id = excluded.task_id,
                    status = excluded.status,
                    mode = excluded.mode,
                    phase = excluded.phase,
                    cycle = excluded.cycle,
                    snapshot_json = excluded.snapshot_json,
                    updated_at = excluded.updated_at
                """,
                (
                    snapshot["run_id"],
                    snapshot["group_chat_id"],
                    snapshot.get("task_id", snapshot.get("snapshot", {}).get("task_id", "")),
                    snapshot["status"],
                    snapshot["mode"],
                    snapshot["phase"],
                    snapshot["cycle"],
                    _encode(snapshot["snapshot"]),
                    snapshot["created_at"],
                    snapshot["updated_at"],
                ),
            )

        _write(self.store, operation)

    def get_snapshot(self, run_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT run_id, group_chat_id, status, mode, phase, cycle,
                       task_id,
                       snapshot_json, created_at, updated_at
                FROM runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "group_chat_id": row["group_chat_id"],
            "status": row["status"],
            "mode": row["mode"],
            "phase": row["phase"],
            "cycle": row["cycle"],
            "task_id": row["task_id"],
            "snapshot": _decode(row["snapshot_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_latest_for_task(self, group_chat_id: str, task_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT run_id FROM runs
                WHERE group_chat_id = ? AND task_id = ?
                ORDER BY updated_at DESC, run_id DESC
                LIMIT 1
                """,
                (group_chat_id, task_id),
            ).fetchone()
        return None if row is None else self.get_snapshot(row["run_id"])

    def save_cursor(self, run_id: str, cursor: int) -> int:
        return _save_cursor(self.store, run_id, cursor)

    def get_cursor(self, run_id: str) -> int:
        return _get_cursor(self.store, run_id)

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                "DELETE FROM runs WHERE group_chat_id = ?", (group_chat_id,)
            ),
        )

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM runs"))


class MeetingRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def append_event(self, event: dict) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT OR IGNORE INTO meeting_events
                    (event_id, run_id, actor_id, actor_role, kind, content,
                     timestamp, source_refs_json, source, phase, sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["run_id"],
                    event["actor_id"],
                    event["actor_role"],
                    event["kind"],
                    event["content"],
                    event["timestamp"],
                    _encode(event.get("source_refs", [])),
                    event.get("source", "live"),
                    event.get("phase", "meeting"),
                    event.get("sequence", 0),
                ),
            )

        _write(self.store, operation)

    def list_events(self, run_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT event_id, run_id, actor_id, actor_role, kind, content,
                       timestamp, source_refs_json, source, phase, sequence
                FROM meeting_events
                WHERE run_id = ?
                ORDER BY timestamp, event_id
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "run_id": row["run_id"],
                "actor_id": row["actor_id"],
                "actor_role": row["actor_role"],
                "kind": row["kind"],
                "content": row["content"],
                "timestamp": row["timestamp"],
                "source_refs": _decode(row["source_refs_json"]),
                "source": row["source"],
                "phase": row["phase"],
                "sequence": row["sequence"],
            }
            for row in rows
        ]

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(
            self.store,
            lambda connection: connection.execute(
                """
                DELETE FROM meeting_events
                WHERE run_id IN (
                    SELECT run_id FROM runs WHERE group_chat_id = ?
                )
                """,
                (group_chat_id,),
            ),
        )

    def delete_for_runs(self, run_ids: list[str]) -> None:
        if not run_ids:
            return

        def operation(connection) -> None:
            placeholders = ",".join("?" for _ in run_ids)
            connection.execute(
                f"DELETE FROM meeting_events WHERE run_id IN ({placeholders})",
                tuple(run_ids),
            )

        _write(self.store, operation)

    def delete_all(self) -> None:
        _write(
            self.store,
            lambda connection: connection.execute("DELETE FROM meeting_events"),
        )


class RuntimeSessionRepository:
    """Persist native session ownership metadata, never transcript content."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def upsert(self, record: dict) -> None:
        now = record.get("updated_at", record.get("created_at", 0.0))
        def operation(connection) -> None:
            existing = connection.execute(
                "SELECT * FROM runtime_sessions WHERE session_id = ?",
                (record["session_id"],),
            ).fetchone()
            if existing is not None:
                for field in ("group_chat_id", "run_id", "agent_id", "phase", "data_space"):
                    if existing[field] != record.get(field, existing[field]):
                        raise ValueError(f"runtime session identity mismatch: {field}")
                if existing["task_id"] and record.get("task_id", "") and existing["task_id"] != record["task_id"]:
                    raise ValueError("runtime session identity mismatch: task_id")
                existing_scope = _decode(existing["document_scope_json"])
                incoming_scope = list(record.get("document_scope", []))
                if existing_scope and incoming_scope and existing_scope != incoming_scope:
                    raise ValueError("runtime session identity mismatch: document_scope")
            connection.execute(
                """
                INSERT INTO runtime_sessions
                    (session_id, group_chat_id, run_id, agent_id, phase,
                     session_scope, session_file, status, last_cursor, data_space,
                     task_id, document_scope_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    last_cursor = MAX(runtime_sessions.last_cursor, excluded.last_cursor),
                    session_file = excluded.session_file,
                    task_id = CASE WHEN excluded.task_id != '' THEN excluded.task_id ELSE runtime_sessions.task_id END,
                    document_scope_json = CASE WHEN excluded.document_scope_json != '[]'
                        THEN excluded.document_scope_json ELSE runtime_sessions.document_scope_json END,
                    updated_at = excluded.updated_at
                """,
                (
                    record["session_id"], record["group_chat_id"], record["run_id"],
                    record["agent_id"], record["phase"], record.get("session_scope", ""),
                    record.get("session_file"), record.get("status", "active"),
                    record.get("last_cursor", 0), record.get("data_space", "synthetic"),
                    record.get("task_id", ""), _encode(record.get("document_scope", [])),
                    record.get("created_at", now), now,
                ),
            )

        _write(self.store, operation)

    def get(self, session_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute("SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)).fetchone()
        return None if row is None else self._from_row(row)

    def list_for_run(self, run_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_sessions WHERE run_id = ? ORDER BY updated_at, session_id", (run_id,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row) -> dict:
        value = dict(row)
        value["document_scope"] = _decode(value.pop("document_scope_json", "[]"))
        return value

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(self.store, lambda connection: connection.execute(
            "DELETE FROM runtime_sessions WHERE group_chat_id = ?", (group_chat_id,)
        ))

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM runtime_sessions"))


class RuntimeEventRepository:
    """Idempotent ordered runtime event log used for cursor recovery."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def append_once(self, event: dict) -> bool:
        def operation(connection) -> None:
            existing = connection.execute(
                """
                SELECT event_id FROM runtime_events
                WHERE run_id = ? AND session_id = ? AND cursor = ?
                """,
                (event["run_id"], event["session_id"], event["cursor"]),
            ).fetchone()
            if existing is not None:
                return False
            connection.execute(
                """
                INSERT INTO runtime_events
                    (event_id, run_id, group_chat_id, session_id, agent_id,
                     phase, event_type, cursor, invocation_id, payload_json,
                     data_space, task_id, document_scope_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"], event["run_id"], event["group_chat_id"],
                    event["session_id"], event["agent_id"], event["phase"],
                    event["type"], event["cursor"], event["invocation_id"],
                    _encode(event.get("payload", {})), event.get("data_space", "synthetic"),
                    event.get("task_id", ""), _encode(event.get("document_scope", [])),
                    event["timestamp"],
                ),
            )
            connection.execute(
                """
                INSERT INTO runtime_cursors(run_id, cursor, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    cursor = MAX(runtime_cursors.cursor, excluded.cursor),
                    updated_at = excluded.updated_at
                """,
                (event["run_id"], event["cursor"], event["timestamp"]),
            )
            return True
        if self.store.in_transaction:
            return operation(self.store.connection())
        with self.store.transaction() as connection:
            return operation(connection)

    def append(self, event: dict) -> None:
        """Backward-compatible alias for idempotent event append."""
        self.append_once(event)

    def save_cursor(self, run_id: str, cursor: int) -> int:
        return _save_cursor(self.store, run_id, cursor)

    def get_cursor(self, run_id: str) -> int:
        return _get_cursor(self.store, run_id)

    def list_for_run(self, run_id: str, *, after: int = 0) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT event_id, run_id, group_chat_id, session_id, agent_id,
                       phase, event_type, cursor, invocation_id, payload_json,
                       data_space, task_id, document_scope_json, timestamp
                FROM runtime_events WHERE run_id = ? AND cursor > ?
                ORDER BY cursor, event_id
                """, (run_id, after),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"], "run_id": row["run_id"],
                "group_chat_id": row["group_chat_id"], "session_id": row["session_id"],
                "agent_id": row["agent_id"], "phase": row["phase"],
                "type": row["event_type"], "cursor": row["cursor"],
                "invocation_id": row["invocation_id"], "payload": _decode(row["payload_json"]),
                "data_space": row["data_space"], "task_id": row["task_id"],
                "document_scope": _decode(row["document_scope_json"]),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def delete_for_group(self, group_chat_id: str) -> None:
        _write(self.store, lambda connection: connection.execute(
            "DELETE FROM runtime_events WHERE group_chat_id = ?", (group_chat_id,)
        ))

    def delete_all(self) -> None:
        _write(self.store, lambda connection: connection.execute("DELETE FROM runtime_events"))


class CandidateRepository:
    """Persist candidate claims, their located refs, and formal projections."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, candidate: dict, evidence: list[dict]) -> None:
        def operation(connection) -> None:
            connection.execute(
                """
                INSERT INTO candidate_claims
                    (candidate_id, task_id, run_id, group_chat_id, agent_id,
                     claim, reasoning_summary, uncertainty, next_action,
                     data_space, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["candidate_id"], candidate["task_id"], candidate["run_id"],
                    candidate["group_chat_id"], candidate["agent_id"], candidate["claim"],
                    candidate["reasoning_summary"], candidate["uncertainty"], candidate["next_action"],
                    candidate["data_space"], candidate.get("status", "candidate"),
                    candidate["created_at"], candidate["updated_at"],
                ),
            )
            legacy_evidence = [item for item in evidence if item.get("source_type", "user_uploaded") == "user_uploaded"]
            connection.executemany(
                """
                INSERT INTO candidate_evidence_refs
                    (candidate_id, evidence_ref, position, document_id, verification_status)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        candidate["candidate_id"], item["chunk_id"], position,
                        item["document_id"], item.get("verification_status", "pending"),
                    )
                    for position, item in enumerate(legacy_evidence)
                ],
            )

        _write(self.store, operation)

    def get(self, candidate_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT * FROM candidate_claims WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
            if row is None:
                return None
            generic_refs = connection.execute(
                """
                SELECT e.source_ref, e.source_type, e.source_data_space,
                       e.verification_status, e.locator, e.extraction_summary,
                       sl.locator_json
                FROM candidate_evidence_links l
                JOIN evidence_records e ON e.evidence_id = l.evidence_id
                LEFT JOIN evidence_source_links sl
                  ON sl.evidence_id = e.evidence_id AND sl.source_ref = e.source_ref
                WHERE l.candidate_id = ? ORDER BY l.position
                """,
                (candidate_id,),
            ).fetchall()
            refs = connection.execute(
                """
                SELECT r.evidence_ref, r.document_id, r.verification_status
                     , d.data_space, c.page_or_location, c.char_start, c.char_end
                FROM candidate_evidence_refs r
                JOIN documents d ON d.document_id = r.document_id
                JOIN document_chunks c ON c.chunk_id = r.evidence_ref
                WHERE r.candidate_id = ? ORDER BY r.position
                """,
                (candidate_id,),
            ).fetchall()
        if generic_refs:
            from app.experiments.repository import ExperimentDatasetRepository
            from app.literature.repository import LiteratureLeadRepository

            experiment_repository = ExperimentDatasetRepository(self.store)
            literature_repository = LiteratureLeadRepository(self.store)
            evidence = []
            for item in generic_refs:
                locator = _decode(item["locator_json"]) if item["locator_json"] else {}
                if not isinstance(locator, dict):
                    locator = {}
                is_uploaded = item["source_type"] == "user_uploaded"
                resolved = {
                    "source_ref": item["source_ref"],
                    "chunk_id": locator.get("chunk_id") if is_uploaded else None,
                    "document_id": locator.get("document_id") if is_uploaded else None,
                    "group_chat_id": locator.get("group_chat_id") or row["group_chat_id"],
                    "data_space": locator.get("data_space") or item["source_data_space"],
                    "source_type": item["source_type"],
                    "verification_status": locator.get("verification_status") or item["verification_status"],
                    "page_or_location": locator.get("page_or_location") or item["locator"],
                    "char_start": locator.get("char_start", 0) if is_uploaded else 0,
                    "char_end": locator.get("char_end", 0) if is_uploaded else 0,
                    "analysis_id": None,
                    "dataset_id": None,
                    "dataset_version": None,
                    "source_filename": locator.get("source_filename"),
                    "source_url": locator.get("source_url"),
                }
                if item["source_type"] == "experiment" and item["source_ref"].startswith("analysis:"):
                    analysis_id = item["source_ref"].removeprefix("analysis:")
                    analysis = experiment_repository.get_analysis(analysis_id)
                    if analysis is not None:
                        dataset = experiment_repository.get(analysis.dataset_id, analysis.dataset_version)
                        resolved.update({
                            "analysis_id": analysis.analysis_id,
                            "dataset_id": analysis.dataset_id,
                            "dataset_version": analysis.dataset_version,
                            "source_filename": dataset.filename if dataset is not None else None,
                            "page_or_location": (
                                f"{dataset.filename} v{analysis.dataset_version}"
                                if dataset is not None else item["locator"]
                            ),
                        })
                elif item["source_type"] == "literature":
                    lead = literature_repository.get(item["source_ref"])
                    if lead is not None:
                        resolved["source_url"] = lead.url
                evidence.append(resolved)
            evidence_refs = [item["source_ref"] for item in generic_refs]
        else:
            evidence = [
                {
                    "source_ref": item["evidence_ref"],
                    "chunk_id": item["evidence_ref"],
                    "document_id": item["document_id"],
                    "group_chat_id": row["group_chat_id"],
                    "data_space": item["data_space"],
                    "source_type": "user_uploaded",
                    "verification_status": item["verification_status"],
                    "page_or_location": item["page_or_location"] or "document",
                    "char_start": item["char_start"] or 0,
                    "char_end": item["char_end"] or 0,
                }
                for item in refs
            ]
            evidence_refs = [item["evidence_ref"] for item in refs]
        return {
            **dict(row),
            "evidence_refs": evidence_refs,
            "evidence_documents": {
                item["evidence_ref"]: item["document_id"] for item in refs
            },
            "evidence": evidence,
        }

    def list_for_run(self, run_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                "SELECT candidate_id FROM candidate_claims WHERE run_id = ? ORDER BY created_at, candidate_id",
                (run_id,),
            ).fetchall()
        return [item for row in rows if (item := self.get(row["candidate_id"])) is not None]

    def scope(self, candidate: dict):
        """Build validation scope from task documents and the frozen Run."""
        from app.literature.repository import LiteratureLeadRepository
        from app.experiments.repository import ExperimentDatasetRepository
        from app.research.contracts import CandidateEvidenceRef, CandidateScope
        from app.tools.audit_repository import ToolAuditRepository

        with self.store.locked() as connection:
            task = connection.execute(
                "SELECT * FROM research_tasks WHERE task_id = ?", (candidate["task_id"],)
            ).fetchone()
            run = connection.execute(
                "SELECT group_chat_id, task_id, snapshot_json FROM runs WHERE run_id = ?",
                (candidate["run_id"],),
            ).fetchone()
            if task is None or run is None:
                raise ValueError("candidate task or run does not exist")
            if run["task_id"] != candidate["task_id"] or run["group_chat_id"] != task["group_chat_id"]:
                raise ValueError("candidate task and run binding is invalid")
            snapshot = _decode(run["snapshot_json"])
            successful_source_refs = ToolAuditRepository(self.store).list_successful_source_refs(
                candidate["run_id"], candidate["agent_id"]
            )
            agent_ids = {
                str(item.get("agent_id"))
                for item in snapshot.get("agent_specs", [])
                if isinstance(item, dict)
            }
            review_agent = snapshot.get("review_agent_spec", {})
            if isinstance(review_agent, dict):
                agent_ids.add(str(review_agent.get("agent_id", "")))
            if candidate["agent_id"] not in agent_ids:
                raise ValueError("candidate agent_id is not part of the Run")
            document_rows = connection.execute(
                """
                SELECT d.document_id, d.group_chat_id, d.data_space, d.status,
                       j.status AS index_status
                FROM task_documents td
                JOIN documents d ON d.document_id = td.document_id
                JOIN document_index_jobs j ON j.document_id = d.document_id
                WHERE td.task_id = ? ORDER BY td.position
                """,
                (candidate["task_id"],),
            ).fetchall()
            chunks = connection.execute(
                """
                SELECT c.chunk_id, c.document_id, d.group_chat_id, d.data_space,
                       c.page_or_location, c.char_start, c.char_end,
                       d.status, j.status AS index_status
                FROM document_chunks c
                JOIN documents d ON d.document_id = c.document_id
                JOIN document_index_jobs j ON j.document_id = c.document_id
                JOIN task_documents td ON td.document_id = c.document_id
                WHERE td.task_id = ? ORDER BY c.chunk_index, c.chunk_id
                """,
                (candidate["task_id"],),
            ).fetchall()
        available: dict[str, CandidateEvidenceRef] = {}
        for row in chunks:
            if row["status"] != "ready" or row["index_status"] != "ready":
                continue
            if successful_source_refs and row["chunk_id"] not in successful_source_refs:
                continue
            available[row["chunk_id"]] = CandidateEvidenceRef(
                chunk_id=row["chunk_id"], document_id=row["document_id"],
                group_chat_id=row["group_chat_id"], data_space=row["data_space"],
                page_or_location=row["page_or_location"], char_start=row["char_start"],
                char_end=row["char_end"], source_ref=row["chunk_id"],
            )
        literature_repository = LiteratureLeadRepository(self.store)
        for source_ref in sorted(ref for ref in successful_source_refs if ref.startswith("literature:")):
            lead = literature_repository.get(source_ref)
            if lead is None:
                continue
            available[source_ref] = CandidateEvidenceRef(
                group_chat_id=task["group_chat_id"], data_space=lead.data_space,
                source_type="literature", verification_status=lead.verification_status,
                page_or_location=lead.source_location, source_ref=source_ref,
                source_url=lead.url,
            )
        experiment_repository = ExperimentDatasetRepository(self.store)
        for source_ref in sorted(ref for ref in successful_source_refs if ref.startswith("analysis:")):
            analysis = experiment_repository.get_analysis(source_ref.removeprefix("analysis:"))
            if analysis is None:
                continue
            dataset = experiment_repository.get(analysis.dataset_id, analysis.dataset_version)
            if dataset is None or dataset.group_chat_id != task["group_chat_id"]:
                continue
            available[source_ref] = CandidateEvidenceRef(
                group_chat_id=task["group_chat_id"], data_space=analysis.data_space,
                source_type="experiment", verification_status="verified",
                page_or_location=f"{dataset.filename} v{analysis.dataset_version}",
                source_ref=source_ref, analysis_id=analysis.analysis_id,
                dataset_id=analysis.dataset_id, dataset_version=analysis.dataset_version,
                source_filename=dataset.filename,
            )
        return CandidateScope(
            group_chat_id=task["group_chat_id"], task_id=task["task_id"],
            run_id=candidate["run_id"], agent_id=candidate["agent_id"],
            data_space=task["data_space"],
            document_scope=[row["document_id"] for row in document_rows],
            available_evidence_refs=available,
            successful_source_refs=successful_source_refs,
        )

    def update_status(self, candidate_id: str, status: str, updated_at: float, connection=None) -> None:
        target = connection or self.store.connection()
        cursor = target.execute(
            "UPDATE candidate_claims SET status = ?, updated_at = ? WHERE candidate_id = ?",
            (status, updated_at, candidate_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(candidate_id)

    def delete_all(self) -> None:
        _write(self.store, lambda connection: (
            connection.execute("DELETE FROM candidate_evidence_refs"),
            connection.execute("DELETE FROM candidate_claims"),
            connection.execute("DELETE FROM claim_approvals"),
            connection.execute("DELETE FROM formal_claims"),
        ))
