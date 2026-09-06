"""Fixed, read-only synthetic tool adapters."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.tools.errors import ToolArgumentsError
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest, ToolResult, ToolSpec

_BOUNDARY = ["read-only", "synthetic", "demo-only", "candidate-context-only"]
_MEMORY_KINDS = {
    "Claim", "Decision", "ResearchState", "ExperimentPlan", "ExperimentResult",
    "HypothesisUpdate", "DiscussionTurn", "PostdocExchange", "ReviewGate", "Disposition",
}


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _arguments(request: ToolRequest, allowed: set[str]) -> dict[str, Any]:
    unknown = set(request.arguments) - allowed
    if unknown:
        raise ToolArgumentsError(f"unsupported arguments: {sorted(unknown)}")
    return request.arguments


def memory_query(request: ToolRequest, context) -> ToolResult:
    args = _arguments(request, {"kind", "object_key", "version", "query"})
    kind = args.get("kind")
    if kind is not None and (not isinstance(kind, str) or kind not in _MEMORY_KINDS):
        raise ToolArgumentsError("kind must be a known memory kind")
    object_key = args.get("object_key")
    if object_key is not None and (not isinstance(object_key, str) or not object_key.strip()):
        raise ToolArgumentsError("object_key must be non-empty text")
    version = args.get("version")
    if version is not None and (not isinstance(version, int) or isinstance(version, bool) or version < 1):
        raise ToolArgumentsError("version must be a positive integer")
    query = args.get("query")
    if query is not None and (not isinstance(query, str) or len(query) > 200):
        raise ToolArgumentsError("query must be at most 200 characters")
    allowed_refs = set(context.input_refs)
    items = []
    for entry in context.memory_entries:
        if allowed_refs and entry.get("id") not in allowed_refs:
            continue
        if entry.get("data_space", "synthetic") != "synthetic":
            continue
        if kind is not None and entry.get("kind") != kind:
            continue
        if object_key is not None and entry.get("object_key") != object_key:
            continue
        if version is not None and entry.get("version") != version:
            continue
        payload = entry.get("payload", {})
        searchable = str(payload) if isinstance(payload, Mapping) else ""
        if query and query.casefold() not in searchable.casefold():
            continue
        items.append({
            key: entry.get(key)
            for key in ("id", "kind", "object_key", "version", "supersedes", "data_space")
        })
        if len(items) >= context.limits.max_items:
            break
    return ToolResult(
        request_id=request.request_id, name=request.name, version="1.0", status="ok",
        payload={"items": items, "count": len(items), "read_only": True},
        source_refs=[item["id"] for item in items if isinstance(item.get("id"), str)],
        boundary_notes=_BOUNDARY + ["memory entries are candidate context, not formal writes"],
    )


def memory_spec() -> ToolSpec:
    return ToolSpec(
        name="memory.query", version="1.0", description="Query current synthetic memory snapshot",
        read_only=True, input_schema={"type": "object", "properties": {"kind": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        allowed_roles=["master_student"], allowed_phases=["independent_analysis"],
        data_spaces=["synthetic"], result_limits={"max_items": 10, "max_bytes": 8192},
    )


def register_memory_tool(registry: ToolRegistry) -> None:
    registry.register(memory_spec(), memory_query)


def literature_search(request: ToolRequest, context) -> ToolResult:
    args = _arguments(request, {"query", "status", "limit"})
    query = args.get("query", "")
    if not isinstance(query, str) or len(query) > 200:
        raise ToolArgumentsError("query must be text of at most 200 characters")
    status = args.get("status")
    if status is not None and status not in {"lead", "pending"}:
        raise ToolArgumentsError("status must be lead or pending")
    limit = args.get("limit", context.limits.max_items)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= context.limits.max_items:
        raise ToolArgumentsError(f"limit must be between 1 and {context.limits.max_items}")
    items = []
    for lead in context.literature_leads:
        if lead.get("status") not in {"lead", "pending"}:
            continue
        if status is not None and lead.get("status") != status:
            continue
        haystack = f"{lead.get('title', '')} {lead.get('summary', '')}".casefold()
        if query and query.casefold() not in haystack:
            continue
        items.append({
            "local_key": lead.get("local_key"), "title": lead.get("title"),
            "summary": lead.get("summary"), "status": lead.get("status"),
            "source": "demo_data/foam_concrete_case/literature_leads",
            "synthetic_notice": "synthetic demo lead; requires independent verification",
        })
        if len(items) >= limit:
            break
    return ToolResult(
        request_id=request.request_id, name=request.name, version="1.0", payload={"items": items, "count": len(items)},
        source_refs=[item["local_key"] for item in items if isinstance(item.get("local_key"), str)],
        boundary_notes=_BOUNDARY + ["non-evidence", "literature leads are not verified evidence"],
    )


def literature_spec() -> ToolSpec:
    return ToolSpec(
        name="literature.search", version="1.0", description="Search fixed synthetic literature leads",
        read_only=True, input_schema={"type": "object", "properties": {"query": {"type": "string"}, "status": {"enum": ["lead", "pending"]}}},
        output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        allowed_roles=["master_student"], allowed_phases=["independent_analysis"],
        data_spaces=["synthetic"], result_limits={"max_items": 10, "max_bytes": 8192},
    )


def register_literature_tool(registry: ToolRegistry) -> None:
    registry.register(literature_spec(), literature_search)


def experiment_analyze_demo(request: ToolRequest, context) -> ToolResult:
    args = _arguments(request, {"mode", "condition", "compare"})
    mode = args.get("mode", "summary")
    if mode not in {"summary", "compare"}:
        raise ToolArgumentsError("mode must be summary or compare")
    condition = args.get("condition")
    if condition is not None and (not isinstance(condition, str) or len(condition) > 120):
        raise ToolArgumentsError("condition must be text of at most 120 characters")
    compare = args.get("compare")
    if compare is not None and (not isinstance(compare, str) or len(compare) > 120):
        raise ToolArgumentsError("compare must be text of at most 120 characters")
    view = context.experiment_view
    plan = view.get("plan") if isinstance(view, Mapping) else None
    results = view.get("results") if isinstance(view, Mapping) else None
    rows = results.get("rows", ()) if isinstance(results, Mapping) else ()
    rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    if condition:
        rows = [row for row in rows if row.get("condition") == condition]
    rows = rows[:context.limits.max_items]
    updates = view.get("hypothesis_updates", ()) if isinstance(view, Mapping) else ()
    statuses = {item.get("status") for item in updates if isinstance(item, Mapping)}
    if "supported" in statuses:
        assessment = "supports"
    elif "weakened" in statuses:
        assessment = "weakened"
    else:
        assessment = "supports" if rows else "inconclusive"
    payload = {
        "mode": mode, "constraints": _thaw(view.get("constraints", {})),
        "plan": _thaw(plan) if isinstance(plan, Mapping) else None,
        "results": {"source": results.get("source"), "rows": _thaw(rows)} if isinstance(results, Mapping) else None,
        "support_assessment": assessment,
        "posterior_interpretation": bool("posterior" in statuses),
        "read_only": True,
    }
    return ToolResult(
        request_id=request.request_id, name=request.name, version="1.0", payload=payload,
        source_refs=[str(results.get("source"))] if isinstance(results, Mapping) and results.get("source") else [],
        boundary_notes=_BOUNDARY + ["correlation or agreement is not causal proof", "missing sample chain, conditions or results remain 待补证"],
    )


def experiment_spec() -> ToolSpec:
    return ToolSpec(
        name="experiment.analyze_demo", version="1.0", description="Analyze current synthetic experiment projection",
        read_only=True, input_schema={"type": "object", "properties": {"mode": {"enum": ["summary", "compare"]}}},
        output_schema={"type": "object", "properties": {"support_assessment": {"type": "string"}}},
        allowed_roles=["master_student"], allowed_phases=["independent_analysis"],
        data_spaces=["synthetic"], result_limits={"max_items": 10, "max_bytes": 8192},
    )


def register_experiment_tool(registry: ToolRegistry) -> None:
    registry.register(experiment_spec(), experiment_analyze_demo)
