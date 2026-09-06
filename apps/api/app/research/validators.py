"""Pure validation for candidate claims and their source references."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from app.research.contracts import CandidateClaim, CandidateScope, ValidatedCandidate


class ResultValidationError(ValueError):
    """A runtime result cannot be projected as a research candidate."""

    code = "result_invalid"


def _candidate(value: CandidateClaim | Mapping[str, object]) -> CandidateClaim:
    try:
        return value if isinstance(value, CandidateClaim) else CandidateClaim.model_validate(value)
    except ValidationError as exc:
        fields = [str(item["loc"][-1]) for item in exc.errors() if item.get("loc")]
        field = fields[0] if fields else "candidate"
        raise ResultValidationError(f"{field} is invalid") from exc


def validate_candidate(
    candidate: CandidateClaim | Mapping[str, object],
    scope: CandidateScope | Mapping[str, object],
) -> ValidatedCandidate:
    """Validate identity, data space and every located evidence reference."""
    value = _candidate(candidate)
    try:
        resolved_scope = scope if isinstance(scope, CandidateScope) else CandidateScope.model_validate(scope)
    except ValidationError as exc:
        raise ResultValidationError("candidate validation scope is invalid") from exc
    if value.status != "candidate":
        raise ResultValidationError("candidate status must be candidate")
    for field in ("task_id", "run_id", "agent_id", "data_space"):
        if getattr(value, field) != getattr(resolved_scope, field):
            raise ResultValidationError(
                f"{field} mismatch: expected {getattr(resolved_scope, field)}"
            )
    if not value.claim.strip():
        raise ResultValidationError("claim must be non-empty text")
    if not value.evidence_refs:
        raise ResultValidationError("evidence_refs must not be empty")

    resolved: list = []
    for evidence_ref in value.evidence_refs:
        if evidence_ref.startswith(("literature:", "analysis:")) and evidence_ref not in resolved_scope.successful_source_refs:
            raise ResultValidationError(f"evidence_ref was not returned by a successful tool call: {evidence_ref}")
        source = resolved_scope.available_evidence_refs.get(evidence_ref)
        if source is None:
            raise ResultValidationError(f"evidence_ref does not exist: {evidence_ref}")
        if source.group_chat_id != resolved_scope.group_chat_id:
            raise ResultValidationError(f"evidence_ref group scope denied: {evidence_ref}")
        if source.source_type == "literature":
            if resolved_scope.data_space not in {"real", "desensitized_real"} or source.data_space != "verifiable_public":
                raise ResultValidationError(f"evidence_ref data_space mismatch: {evidence_ref}")
        elif source.data_space != resolved_scope.data_space:
            raise ResultValidationError(f"evidence_ref data_space mismatch: {evidence_ref}")
        if source.source_type == "user_uploaded" and source.document_id not in resolved_scope.document_scope:
            raise ResultValidationError(f"evidence_ref document scope denied: {evidence_ref}")
        if source.verification_status in {"unavailable", "rejected"}:
            raise ResultValidationError(f"evidence_ref verification status is invalid: {evidence_ref}")
        resolved.append(source)
    return ValidatedCandidate(
        **value.model_dump(mode="python", exclude={"evidence"}),
        evidence=resolved,
    )
