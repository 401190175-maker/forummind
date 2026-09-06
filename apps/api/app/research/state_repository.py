"""Append-only ResearchState persistence used by approval transactions."""

from __future__ import annotations

import json

from app.storage.sqlite_store import SQLiteStore


class ResearchStateRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def append_for_approved_claim(
        self, connection, candidate: dict, formal_claim: dict, evidence: list[dict],
    ) -> dict:
        row = connection.execute(
            """
            SELECT state_id, version FROM group_research_state_heads
            WHERE group_chat_id = ?
            """,
            (candidate["group_chat_id"],),
        ).fetchone()
        previous_state_id = None if row is None else row["state_id"]
        version = 1 if row is None else int(row["version"]) + 1
        state_id = f"state:{candidate['group_chat_id']}:v{version}"
        evidence_ids = [str(item["evidence_id"]) for item in evidence]
        payload = {
            "state_id": state_id,
            "group_chat_id": candidate["group_chat_id"],
            "version": version,
            "previous_state_id": previous_state_id,
            "formal_claim_id": formal_claim["claim_id"],
            "claim": formal_claim["claim"],
            "data_space": formal_claim["data_space"],
            "evidence_ids": evidence_ids,
            "evidence_status": formal_claim.get("evidence_status", "pending"),
        }
        now = float(formal_claim["created_at"])
        connection.execute(
            """
            INSERT INTO research_state_versions
                (state_id, group_chat_id, version, previous_state_id,
                 formal_claim_id, state_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state_id, candidate["group_chat_id"], version, previous_state_id,
                formal_claim["claim_id"], json.dumps(payload, ensure_ascii=False), now,
            ),
        )
        connection.execute(
            """
            INSERT INTO group_research_state_heads(group_chat_id, state_id, version, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(group_chat_id) DO UPDATE SET
                state_id=excluded.state_id, version=excluded.version,
                updated_at=excluded.updated_at
            """,
            (candidate["group_chat_id"], state_id, version, now),
        )
        connection.executemany(
            """
            INSERT INTO formal_claim_evidence_links
                (claim_id, evidence_id, source_ref, position)
            VALUES (?, ?, ?, ?)
            """,
            [
                (formal_claim["claim_id"], item["evidence_id"], item["source_ref"], position)
                for position, item in enumerate(evidence)
            ],
        )
        return payload

    def get_head(self, group_chat_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT state_id, version, updated_at FROM group_research_state_heads WHERE group_chat_id = ?",
                (group_chat_id,),
            ).fetchone()
            if row is None:
                return None
            state = connection.execute(
                "SELECT state_json FROM research_state_versions WHERE state_id = ?",
                (row["state_id"],),
            ).fetchone()
        return None if state is None else json.loads(state["state_json"])

    def list_versions(self, group_chat_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT state_json FROM research_state_versions
                WHERE group_chat_id = ? ORDER BY version
                """,
                (group_chat_id,),
            ).fetchall()
        return [json.loads(row["state_json"]) for row in rows]
