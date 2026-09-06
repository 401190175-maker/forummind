"""Durable, redacted persistence for terminal tool-call audits."""

from __future__ import annotations

import json

from app.storage.sqlite_store import SQLiteStore
from app.tools.schemas import ToolCallRecord


class ToolAuditRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def append(self, record: ToolCallRecord) -> None:
        with self.store.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO tool_call_audits
                    (record_id, run_id, group_chat_id, agent_id, status,
                     source_refs_json, record_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id, record.run_id, record.group_chat_id,
                    record.agent_id, record.status,
                    json.dumps(record.source_refs, ensure_ascii=False),
                    json.dumps(record.model_dump(mode="json"), ensure_ascii=False),
                    record.started_at,
                ),
            )

    def list_for_run(self, run_id: str) -> list[ToolCallRecord]:
        with self.store.locked() as connection:
            rows = connection.execute(
                "SELECT record_json FROM tool_call_audits WHERE run_id = ? ORDER BY created_at, record_id",
                (run_id,),
            ).fetchall()
        return [ToolCallRecord.model_validate(json.loads(row["record_json"])) for row in rows]

    def list_successful_source_refs(self, run_id: str, agent_id: str | None = None) -> set[str]:
        statement = "SELECT source_refs_json FROM tool_call_audits WHERE run_id = ? AND status = 'success'"
        parameters: list[object] = [run_id]
        if agent_id is not None:
            statement += " AND agent_id = ?"
            parameters.append(agent_id)
        with self.store.locked() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        refs: set[str] = set()
        for row in rows:
            refs.update(str(item) for item in json.loads(row["source_refs_json"]))
        return refs
