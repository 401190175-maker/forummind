"""Candidate Claim validation, persistence, and approval transaction."""

from __future__ import annotations

import time
from collections.abc import Mapping
from uuid import uuid4

from app.agent_runtime.schemas import AgentResult
from app.research.contracts import CandidateClaim, ValidatedCandidate
from app.research.evidence_service import EvidenceService
from app.research.state_service import ResearchStateService
from app.research.validators import ResultValidationError, validate_candidate
from app.storage.repositories import CandidateRepository
from app.storage.sqlite_store import SQLiteStore


class CandidateServiceError(ValueError):
    """Base class for candidate service errors."""


class CandidateNotFoundError(CandidateServiceError):
    pass


class ApprovalConflictError(CandidateServiceError):
    code = "approval_conflict"


class CandidateService:
    """Own the boundary between runtime output and formal research objects."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        self.repository = CandidateRepository(store)
        self.evidence_service = EvidenceService(store)
        self.state_service = ResearchStateService(store)
        self.last_error = ""

    def create(self, candidate: CandidateClaim | Mapping[str, object]) -> CandidateClaim:
        try:
            value = candidate if isinstance(candidate, CandidateClaim) else CandidateClaim.model_validate(candidate)
        except Exception as exc:
            raise ResultValidationError(f"candidate result is invalid: {exc}") from exc
        raw = value.model_dump(mode="python")
        try:
            scope = self.repository.scope(raw)
        except ValueError as exc:
            raise ResultValidationError(str(exc)) from exc
        validated = validate_candidate(value, scope)
        now = time.time()
        stored = validated.model_copy(update={"created_at": now, "updated_at": now})
        payload = stored.model_dump(mode="python")
        payload["group_chat_id"] = scope.group_chat_id
        with self.store.transaction():
            self.repository.save(payload, [item.model_dump(mode="python") for item in validated.evidence])
            self.evidence_service.persist_candidate_sources(
                stored.candidate_id,
                list(value.evidence_refs),
                scope.available_evidence_refs,
            )
        return stored

    def from_agent_result(
        self,
        result: AgentResult,
        *,
        task_id: str,
        run_id: str,
        agent_id: str,
        candidate_id: str | None = None,
    ) -> CandidateClaim:
        if result.status != "ok":
            raise ResultValidationError("Agent result status must be ok")
        if result.agent_id != agent_id:
            raise ResultValidationError("agent_id mismatch")
        output = result.structured_output
        if not isinstance(output, Mapping):
            raise ResultValidationError("structured_output must be an object")
        required = ("claim", "evidence_refs", "reasoning_summary", "uncertainty", "next_action")
        missing = [field for field in required if field not in output]
        if missing:
            raise ResultValidationError(f"missing candidate fields: {', '.join(missing)}")
        try:
            candidate = CandidateClaim(
                candidate_id=candidate_id or f"candidate-{uuid4().hex}",
                task_id=task_id, run_id=run_id, agent_id=agent_id,
                claim=output["claim"], evidence_refs=output["evidence_refs"],
                reasoning_summary=output["reasoning_summary"],
                uncertainty=output["uncertainty"], next_action=output["next_action"],
                data_space=result.data_space, status="candidate",
            )
        except Exception as exc:
            raise ResultValidationError(f"candidate output is invalid: {exc}") from exc
        return self.create(candidate)

    def get(self, candidate_id: str) -> CandidateClaim | None:
        record = self.repository.get(candidate_id)
        return None if record is None else self._model(record)

    def list_for_run(self, run_id: str) -> list[CandidateClaim]:
        return [self._model(record) for record in self.repository.list_for_run(run_id)]

    def approve(self, candidate_id: str, actor_id: str) -> CandidateClaim:
        self.last_error = ""
        actor_id = actor_id.strip()
        if not actor_id:
            raise ValueError("actor_id must be non-empty")
        with self.store.transaction() as connection:
            record = self.repository.get(candidate_id)
            if record is None:
                raise CandidateNotFoundError(candidate_id)
            if record["status"] == "approved":
                return self._model(record)
            if record["status"] == "rejected":
                self.last_error = ApprovalConflictError.code
                raise ApprovalConflictError("candidate has already been rejected")
            now = time.time()
            connection.execute(
                """
                INSERT INTO claim_approvals(candidate_id, actor_id, decision, reason, created_at)
                VALUES (?, ?, 'approved', '', ?)
                """,
                (candidate_id, actor_id, now),
            )
            self.repository.update_status(candidate_id, "approved", now, connection)
            connection.execute(
                """
                INSERT INTO formal_claims
                    (claim_id, candidate_id, task_id, run_id, group_chat_id,
                     agent_id, claim, data_space, evidence_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    f"claim:{candidate_id}", candidate_id, record["task_id"], record["run_id"],
                    record["group_chat_id"], record["agent_id"], record["claim"],
                    record["data_space"], now,
                ),
            )
            formal_claim = {
                "claim_id": f"claim:{candidate_id}",
                "candidate_id": candidate_id,
                "claim": record["claim"],
                "data_space": record["data_space"],
                "evidence_status": "pending",
                "created_at": now,
            }
            evidence = self.evidence_service.repository.list_for_candidate(candidate_id)
            self.state_service.append_for_approved_claim(connection, record, formal_claim, evidence)
            record["status"] = "approved"
            record["updated_at"] = now
        return self._model(record)

    def reject(self, candidate_id: str, actor_id: str, reason: str = "") -> CandidateClaim:
        self.last_error = ""
        actor_id = actor_id.strip()
        reason = reason.strip()
        if not actor_id:
            raise ValueError("actor_id must be non-empty")
        with self.store.transaction() as connection:
            record = self.repository.get(candidate_id)
            if record is None:
                raise CandidateNotFoundError(candidate_id)
            if record["status"] == "rejected":
                return self._model(record)
            if record["status"] == "approved":
                self.last_error = ApprovalConflictError.code
                raise ApprovalConflictError("candidate has already been approved")
            now = time.time()
            connection.execute(
                """
                INSERT INTO claim_approvals(candidate_id, actor_id, decision, reason, created_at)
                VALUES (?, ?, 'rejected', ?, ?)
                """,
                (candidate_id, actor_id, reason, now),
            )
            self.repository.update_status(candidate_id, "rejected", now, connection)
            record["status"] = "rejected"
            record["updated_at"] = now
        return self._model(record)

    def count_formal_claims(self, candidate_id: str) -> int:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM formal_claims WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
        return int(row["count"])

    def count_approvals(self, candidate_id: str) -> int:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM claim_approvals WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
        return int(row["count"])

    def formal_evidence_status(self, candidate_id: str) -> str | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT evidence_status FROM formal_claims WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
        return None if row is None else str(row["evidence_status"])

    @staticmethod
    def _model(record: Mapping[str, object]) -> CandidateClaim:
        fields = {
            key: record[key]
            for key in (
                "candidate_id", "task_id", "run_id", "agent_id", "claim",
                "evidence_refs", "reasoning_summary", "uncertainty", "next_action",
                "data_space", "status", "created_at", "updated_at", "evidence",
            )
        }
        return CandidateClaim.model_validate(fields)
