"""Pure validation for candidate results returned by an Agent Runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json

from app.agent_runtime.schemas import AgentInvocation, AgentResult


@dataclass(frozen=True)
class ValidationResult:
    """Whether a candidate satisfies the invocation's output contract."""

    valid: bool
    reason: str = ""
    code: str = ""


_CLAIM_FIELDS = (
    "statement",
    "boundary",
    "prediction",
    "falsification_condition",
)

_RESEARCH_CLAIM_FIELDS = (
    "claim",
    "evidence_refs",
    "reasoning_summary",
    "uncertainty",
    "next_action",
)

_REVIEW_KINDS = {
    "counterexample",
    "falsification_condition",
    "missing_observation",
}
_REVIEW_KIND_ORDER = (
    "counterexample",
    "falsification_condition",
    "missing_observation",
)
_FORBIDDEN_RESULT_KEYS = {
    "option",
    "stage_transition",
    "formal_" + "mem" + "ory_write",
}


def normalize_review_items(value: Mapping[str, object]) -> list[dict] | None:
    """Accept the canonical item list and common provider category arrays."""
    source: Mapping[str, object] = value
    raw_items = source.get("items")
    if raw_items is None:
        nested = value.get("review_result")
        if isinstance(nested, Mapping):
            source = nested
            raw_items = source.get("items")
            if raw_items is None:
                raw_items = source.get("review_items")
    if raw_items is None:
        normalized: list[dict] = []
        for kind in _REVIEW_KIND_ORDER:
            category = source.get(kind)
            if isinstance(category, Mapping):
                category = category.get("items")
            if isinstance(category, str):
                category = [category]
            if not isinstance(category, list):
                return None
            for item in category:
                if isinstance(item, str):
                    content = item
                    normalized_item = {"kind": kind, "content": content}
                elif isinstance(item, Mapping):
                    normalized_item = dict(item)
                    normalized_item.setdefault("kind", kind)
                    content = (
                        item.get("content")
                        or item.get("description")
                        or item.get("statement")
                        or item.get("finding")
                    )
                else:
                    content = None
                if isinstance(content, str):
                    normalized_item["content"] = content
                    normalized.append(normalized_item)
        return normalized
    if not isinstance(raw_items, list):
        return None
    normalized_items: list[dict] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        normalized = dict(item)
        if not isinstance(normalized.get("kind"), str):
            provider_kind = normalized.get("type")
            if isinstance(provider_kind, str):
                normalized["kind"] = provider_kind
        if not isinstance(normalized.get("content"), str):
            for field in ("description", "statement", "finding"):
                value = normalized.get(field)
                if isinstance(value, str):
                    normalized["content"] = value
                    break
        revision = normalized.get("requested_revision")
        content = normalized.get("content")
        if isinstance(content, str) and isinstance(revision, str) and revision.strip():
            normalized["content"] = f"{content.strip()}\n建议修订：{revision.strip()}"
        normalized_items.append(normalized)
    return normalized_items


def _validate_common(
    invocation: AgentInvocation, result: AgentResult
) -> ValidationResult:
    if result.status != "ok":
        return ValidationResult(False, f"result status must be ok, got {result.status}")
    if result.agent_id != invocation.agent_id:
        return ValidationResult(
            False,
            f"agent_id mismatch: expected {invocation.agent_id}, got {result.agent_id}",
        )
    if result.data_space != invocation.data_space:
        return ValidationResult(
            False,
            f"data_space mismatch: expected {invocation.data_space}, got {result.data_space}",
        )
    if not result.content.strip():
        return ValidationResult(False, "content must not be empty")

    if invocation.output_contract == "research_claim":
        for field in _RESEARCH_CLAIM_FIELDS:
            value = result.structured_output.get(field)
            if field == "evidence_refs":
                if not isinstance(value, list) or not value or not all(
                    isinstance(item, str) and item.strip() for item in value
                ):
                    return ValidationResult(
                        False,
                        "research_claim: structured_output.evidence_refs must be a non-empty string list",
                    )
            elif not isinstance(value, str) or not value.strip():
                return ValidationResult(
                    False,
                    f"research_claim: structured_output.{field} must be non-empty text",
                )
        return ValidationResult(True)

    if invocation.output_contract != "claim_four_fields":
        return ValidationResult(True)

    for field in _CLAIM_FIELDS:
        value = result.structured_output.get(field)
        if not isinstance(value, str) or not value.strip():
            return ValidationResult(
                False,
                f"claim_four_fields: structured_output.{field} must be non-empty text",
            )

    return ValidationResult(True)


def _contains_forbidden_action(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_RESULT_KEYS or normalized.startswith("commit_"):
                return True
            if _contains_forbidden_action(nested):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_action(item) for item in value)
    return False


def _postdoc_domain(invocation: AgentInvocation) -> str:
    profile = invocation.context.get("agent_profile", {})
    if not isinstance(profile, Mapping):
        profile = {}
    value = invocation.context.get("specialty_domain") or profile.get("specialty_domain")
    return value.strip() if isinstance(value, str) else ""


def _domain_terms(domain: str) -> list[str]:
    normalized = domain.replace("，", ",").replace("；", ";").replace("、", ",")
    terms = [part.strip() for part in normalized.replace("/", ",").replace(";", ",").split(",")]
    return [term for term in terms if term]


def validate_role_output(
    invocation: AgentInvocation, result: AgentResult
) -> ValidationResult:
    """Enforce role/phase output contracts after a native session settles."""
    common = _validate_common(invocation, result)
    if not common.valid:
        return common
    if invocation.role != "pi" and _contains_forbidden_action(result.structured_output):
        return ValidationResult(
            False,
            f"{invocation.role}/{invocation.phase} result contains a forbidden formal action",
        )

    role_phase = (invocation.role, invocation.phase)
    if role_phase == ("phd_student", "review_gate"):
        if invocation.output_contract != "review_gate":
            return ValidationResult(False, "phd_student/review_gate requires review_gate output contract")
        raw_items = normalize_review_items(result.structured_output)
        if raw_items is None:
            return ValidationResult(False, "phd_student/review_gate requires items or review category arrays")
        kinds: set[str] = set()
        for item in raw_items:
            if not isinstance(item, Mapping):
                return ValidationResult(False, "phd_student/review_gate item must be an object")
            kind = item.get("kind")
            content = item.get("content")
            if kind not in _REVIEW_KINDS or not isinstance(content, str) or not content.strip():
                return ValidationResult(False, "phd_student/review_gate item violates review contract")
            kinds.add(str(kind))
        if kinds != _REVIEW_KINDS:
            return ValidationResult(
                False,
                "phd_student/review_gate must cover counterexample, falsification_condition and missing_observation",
            )
    elif role_phase == ("master_student", "independent_analysis"):
        if invocation.output_contract not in {"claim_four_fields", "research_claim"}:
            return ValidationResult(False, "master_student/independent_analysis requires a claim output contract")
    elif role_phase == ("master_student", "revision"):
        if invocation.output_contract != "revision_dispositions":
            return ValidationResult(False, "master_student/revision requires revision_dispositions")
        if not isinstance(result.structured_output.get("dispositions"), list):
            return ValidationResult(False, "master_student/revision requires dispositions")
    elif invocation.role == "postdoc":
        if invocation.phase != "postdoc_exchange":
            return ValidationResult(False, "postdoc native session is limited to postdoc_exchange")
        domain = _postdoc_domain(invocation)
        if not domain:
            return ValidationResult(False, "postdoc domain_guard requires specialty_domain", "domain_guard")
        text = " ".join(
            [
                result.content,
                json.dumps(result.structured_output, ensure_ascii=False, default=str),
            ]
        )
        if not any(term in text for term in _domain_terms(domain)):
            return ValidationResult(
                False,
                f"domain_guard: response is outside specialty domain {domain}",
                "domain_guard",
            )
    return ValidationResult(True)


def validate_agent_result(
    invocation: AgentInvocation, result: AgentResult
) -> ValidationResult:
    """Validate a runtime result without changing any external state."""
    return validate_role_output(invocation, result)
