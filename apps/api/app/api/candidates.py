"""Browser-facing candidate Claim review endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.api import runs
from app.research.candidate_service import (
    ApprovalConflictError,
    CandidateNotFoundError,
    CandidateService,
)
from app.research.contracts import CandidateClaim
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository


router = APIRouter(tags=["candidates"])
_service: CandidateService | None = None


def configure_persistence(store: SQLiteStore | None) -> None:
    global _service
    _service = CandidateService(store) if store is not None else None


def _dependencies() -> CandidateService:
    if _service is None:
        raise HTTPException(status_code=503, detail="candidate storage is unavailable")
    return _service


def _run(run_id: str):
    state = runs.run_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return state


class CandidateApprovalRequest(BaseModel):
    actor_id: str = Field(default="user", min_length=1, max_length=200)

    @field_validator("actor_id")
    @classmethod
    def _trim_actor(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("actor_id must be non-empty")
        return value


class CandidateRejectionRequest(CandidateApprovalRequest):
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def _trim_reason(cls, value: str) -> str:
        return value.strip()


def _ensure_candidate_run(candidate: CandidateClaim, run_id: str) -> CandidateClaim:
    if candidate.run_id != run_id:
        raise HTTPException(status_code=404, detail="candidate 不属于当前 run")
    return candidate


def _ensure_review_gate(state, candidate: CandidateClaim) -> CandidateClaim:
    if candidate.status == "candidate" and state.status != "awaiting_review":
        raise HTTPException(status_code=409, detail=ApprovalConflictError.code)
    return candidate


@router.get("/runs/{run_id}/candidates", response_model=list[CandidateClaim])
def list_candidates(run_id: str) -> list[CandidateClaim]:
    _run(run_id)
    return _dependencies().list_for_run(run_id)


@router.post(
    "/runs/{run_id}/candidates/{candidate_id}/approve",
    response_model=CandidateClaim,
)
def approve_candidate(
    run_id: str, candidate_id: str, body: CandidateApprovalRequest | None = None
) -> CandidateClaim:
    state = _run(run_id)
    service = _dependencies()
    try:
        candidate = service.get(candidate_id)
        if candidate is None:
            raise CandidateNotFoundError(candidate_id)
        _ensure_candidate_run(candidate, run_id)
        _ensure_review_gate(state, candidate)
        approved = service.approve(candidate_id, (body or CandidateApprovalRequest()).actor_id)
        if approved.status == "approved" and state.status == "awaiting_review":
            state.status = "completed"
            state.phase = "conclusion"
            state.task_context["formal_candidate_id"] = approved.candidate_id
            state.persist()
            ResearchTaskRepository(service.store).set_status(approved.task_id, "completed")
        return approved
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="candidate 不存在") from exc
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail=ApprovalConflictError.code) from exc


@router.post(
    "/runs/{run_id}/candidates/{candidate_id}/reject",
    response_model=CandidateClaim,
)
def reject_candidate(
    run_id: str, candidate_id: str, body: CandidateRejectionRequest | None = None
) -> CandidateClaim:
    state = _run(run_id)
    service = _dependencies()
    try:
        candidate = service.get(candidate_id)
        if candidate is None:
            raise CandidateNotFoundError(candidate_id)
        _ensure_candidate_run(candidate, run_id)
        _ensure_review_gate(state, candidate)
        request = body or CandidateRejectionRequest()
        return service.reject(candidate_id, request.actor_id, request.reason)
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="candidate 不存在") from exc
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail=ApprovalConflictError.code) from exc
