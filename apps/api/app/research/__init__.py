"""Research-task contracts and candidate approval services."""

from app.research.contracts import (
    CandidateClaim,
    CandidateEvidenceRef,
    CandidateScope,
    RealAgentInvocation,
    ValidatedCandidate,
    build_real_invocation,
)

__all__ = [
    "CandidateClaim",
    "CandidateEvidenceRef",
    "CandidateScope",
    "RealAgentInvocation",
    "ValidatedCandidate",
    "build_real_invocation",
]
