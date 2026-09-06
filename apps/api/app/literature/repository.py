"""Durable metadata-only storage for governed literature leads."""

from __future__ import annotations

import json

from app.literature.schemas import LiteratureLead
from app.storage.sqlite_store import SQLiteStore


class LiteratureLeadRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, lead: LiteratureLead, *, retrieved_at: float) -> LiteratureLead:
        with self.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO literature_leads
                    (source_ref, lead_id, doi, url, provider,
                     verification_status, lead_json, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_ref) DO UPDATE SET
                    lead_id=excluded.lead_id, doi=excluded.doi, url=excluded.url,
                    provider=excluded.provider,
                    verification_status=excluded.verification_status,
                    lead_json=excluded.lead_json, retrieved_at=excluded.retrieved_at
                """,
                (
                    lead.source_ref, lead.lead_id, lead.doi, lead.url, lead.provider,
                    lead.verification_status,
                    json.dumps(lead.model_dump(mode="json"), ensure_ascii=False),
                    retrieved_at,
                ),
            )
        return lead

    def get(self, source_ref: str) -> LiteratureLead | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT lead_json FROM literature_leads WHERE source_ref = ?",
                (source_ref,),
            ).fetchone()
        return None if row is None else LiteratureLead.model_validate(json.loads(row["lead_json"]))

    def list_all(self) -> list[LiteratureLead]:
        with self.store.locked() as connection:
            rows = connection.execute(
                "SELECT lead_json FROM literature_leads ORDER BY retrieved_at, source_ref"
            ).fetchall()
        return [LiteratureLead.model_validate(json.loads(row["lead_json"])) for row in rows]
