"""SQLite repositories for typed Evidence and immutable source expansion."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from app.storage.sqlite_store import SQLiteStore


class EvidenceRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, record: Mapping[str, object], source_links: Sequence[Mapping[str, object]]) -> None:
        with self.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO evidence_records
                    (evidence_id, source_ref, source_type, source_data_space,
                     verification_status, applicability_boundary, locator,
                     extraction_summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_ref) DO UPDATE SET
                    source_type=excluded.source_type,
                    source_data_space=excluded.source_data_space,
                    verification_status=excluded.verification_status,
                    applicability_boundary=excluded.applicability_boundary,
                    locator=excluded.locator,
                    extraction_summary=excluded.extraction_summary,
                    updated_at=excluded.updated_at
                """,
                tuple(record[name] for name in (
                    "evidence_id", "source_ref", "source_type", "source_data_space",
                    "verification_status", "applicability_boundary", "locator",
                    "extraction_summary", "created_at", "updated_at",
                )),
            )
            connection.execute(
                "DELETE FROM evidence_source_links WHERE evidence_id = ?",
                (record["evidence_id"],),
            )
            connection.executemany(
                """
                INSERT INTO evidence_source_links
                    (evidence_id, source_ref, position, locator_json)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        record["evidence_id"], link["source_ref"], position,
                        json.dumps(link.get("locator", {}), ensure_ascii=False),
                    )
                    for position, link in enumerate(source_links)
                ],
            )

    def link_candidate(self, candidate_id: str, source_refs: Sequence[str]) -> None:
        with self.store.transaction() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO candidate_evidence_links
                    (candidate_id, evidence_id, source_ref, position)
                SELECT ?, evidence_id, source_ref, ?
                FROM evidence_records WHERE source_ref = ?
                """,
                [(candidate_id, position, source_ref) for position, source_ref in enumerate(source_refs)],
            )

    def get(self, evidence_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_records WHERE evidence_id = ?", (evidence_id,)
            ).fetchone()
            if row is None:
                return None
            links = connection.execute(
                """
                SELECT source_ref, locator_json FROM evidence_source_links
                WHERE evidence_id = ? ORDER BY position
                """,
                (evidence_id,),
            ).fetchall()
        return {
            **dict(row),
            "source_links": [
                {"source_ref": item["source_ref"], "locator": json.loads(item["locator_json"])}
                for item in links
            ],
        }

    def get_by_source_ref(self, source_ref: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT evidence_id FROM evidence_records WHERE source_ref = ?", (source_ref,)
            ).fetchone()
        return None if row is None else self.get(row["evidence_id"])

    def list_for_candidate(self, candidate_id: str) -> list[dict]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT e.* FROM candidate_evidence_links l
                JOIN evidence_records e ON e.evidence_id = l.evidence_id
                WHERE l.candidate_id = ? ORDER BY l.position
                """,
                (candidate_id,),
            ).fetchall()
        return [dict(row) for row in rows]
