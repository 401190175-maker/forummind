"""ResearchState append service with a small public approval primitive."""

from app.research.state_repository import ResearchStateRepository
from app.storage.sqlite_store import SQLiteStore


class ResearchStateService:
    def __init__(self, store: SQLiteStore) -> None:
        self.repository = ResearchStateRepository(store)

    def append_for_approved_claim(self, connection, candidate: dict, formal_claim: dict, evidence: list[dict]) -> dict:
        return self.repository.append_for_approved_claim(connection, candidate, formal_claim, evidence)


def append_for_approved_claim(connection, candidate: dict, formal_claim: dict, evidence: list[dict]) -> dict:
    """Append one immutable state version inside the caller's transaction."""
    return ResearchStateRepository(None).append_for_approved_claim(connection, candidate, formal_claim, evidence)
