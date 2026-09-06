"""Server-owned authorization for Replay and real research tools."""
from __future__ import annotations

from collections.abc import Iterable

from app.tools.context import ToolExecutionContext
from app.tools.schemas import ToolPolicyDecision, ToolRequest, ToolSpec

POLICY_VERSION = "p2-v1"
P2_TOOLS = ["memory.query", "literature.search", "experiment.analyze_demo"]
REAL_TOOLS = ["knowledge.search", "experiment.analyze", "literature.search"]
REAL_ROLES = {"master_student", "phd_student", "postdoc"}
REAL_PHASES = {"independent_analysis", "review_gate"}


def _base_decision(context: ToolExecutionContext) -> ToolPolicyDecision:
    if context.runtime_name != "pi":
        return ToolPolicyDecision(allowed=False, reason="runtime_not_allowed", policy_version=POLICY_VERSION)
    if context.data_space == "synthetic" and context.role != "master_student":
        return ToolPolicyDecision(allowed=False, reason="role_not_allowed", policy_version=POLICY_VERSION)
    if context.data_space in {"real", "desensitized_real"}:
        if context.role not in REAL_ROLES:
            return ToolPolicyDecision(allowed=False, reason="role_not_allowed", policy_version=POLICY_VERSION)
        if context.phase not in REAL_PHASES:
            return ToolPolicyDecision(allowed=False, reason="phase_not_allowed", policy_version=POLICY_VERSION)
        allowed_tools = list(REAL_TOOLS)
        if not context.allowed_dataset_refs:
            allowed_tools.remove("experiment.analyze")
        if context.allowed_tools:
            allowed_tools = [name for name in allowed_tools if name in context.allowed_tools]
        return ToolPolicyDecision(
            allowed=True, reason="allowed", policy_version=POLICY_VERSION,
            allowed_tools=allowed_tools,
        )
    if context.phase != "independent_analysis":
        return ToolPolicyDecision(allowed=False, reason="phase_not_allowed", policy_version=POLICY_VERSION)
    if context.data_space != "synthetic":
        return ToolPolicyDecision(allowed=False, reason="data_space_mismatch", policy_version=POLICY_VERSION)
    return ToolPolicyDecision(allowed=True, reason="allowed", policy_version=POLICY_VERSION, allowed_tools=list(P2_TOOLS))


def resolve_allowed_tools(context: ToolExecutionContext) -> ToolPolicyDecision:
    """Calculate the discoverable tool names from trusted server context."""
    return _base_decision(context)


def authorize_tool(
    request: ToolRequest,
    context: ToolExecutionContext,
    specs: Iterable[ToolSpec],
) -> ToolPolicyDecision:
    """Perform the second authorization check using only server context."""
    base = _base_decision(context)
    spec_by_name = {spec.name: spec for spec in specs}
    if request.name not in spec_by_name:
        return ToolPolicyDecision(allowed=False, reason="not_found", policy_version=POLICY_VERSION, allowed_tools=base.allowed_tools)
    if not base.allowed:
        return ToolPolicyDecision(allowed=False, reason=base.reason, policy_version=POLICY_VERSION, allowed_tools=[])
    spec = spec_by_name[request.name]
    if context.role not in spec.allowed_roles or context.phase not in spec.allowed_phases:
        return ToolPolicyDecision(allowed=False, reason="tool_not_allowed", policy_version=POLICY_VERSION, allowed_tools=base.allowed_tools)
    if context.data_space not in spec.data_spaces:
        return ToolPolicyDecision(allowed=False, reason="data_space_mismatch", policy_version=POLICY_VERSION, allowed_tools=base.allowed_tools)
    if request.data_space != context.data_space:
        return ToolPolicyDecision(allowed=False, reason="data_space_mismatch", policy_version=POLICY_VERSION, allowed_tools=base.allowed_tools)
    if any(ref not in context.input_refs for ref in request.input_refs):
        return ToolPolicyDecision(allowed=False, reason="input_ref_forbidden", policy_version=POLICY_VERSION, allowed_tools=base.allowed_tools)
    return ToolPolicyDecision(allowed=True, reason="allowed", policy_version=POLICY_VERSION, allowed_tools=[request.name])
