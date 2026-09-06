"""Governed Live literature search adapter."""

from __future__ import annotations

from time import time

from app.literature.integration import GovernedLiteratureSearch
from app.literature.repository import LiteratureLeadRepository
from app.literature.schemas import LiteratureFilters
from app.tools.errors import ToolArgumentsError, ToolProviderUnavailable
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest, ToolResult, ToolSpec


def literature_search(request, context, search: GovernedLiteratureSearch, repository: LiteratureLeadRepository) -> ToolResult:
    allowed = {"query", "from_year", "until_year", "max_results", "verify"}
    unknown = set(request.arguments) - allowed
    if unknown:
        raise ToolArgumentsError(f"unsupported arguments: {sorted(unknown)}")
    args = request.arguments
    query = args.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ToolArgumentsError("query must be non-empty text of at most 500 characters")
    verify = args.get("verify", False)
    if not isinstance(verify, bool):
        raise ToolArgumentsError("verify must be boolean")
    try:
        filters = LiteratureFilters(
            from_year=args.get("from_year"),
            until_year=args.get("until_year"),
            max_results=args.get("max_results", context.limits.max_items),
        )
    except Exception as exc:
        raise ToolArgumentsError("invalid literature filters") from exc
    try:
        leads = search.search(query, filters, source_mode="live", verify=verify)
    except Exception as exc:
        raise ToolProviderUnavailable("provider_unavailable") from exc
    for lead in leads:
        repository.save(lead, retrieved_at=time())
    items = [
        {
            "source_ref": lead.source_ref,
            "lead_id": lead.lead_id,
            "title": lead.title,
            "authors": lead.authors[:20],
            "doi": lead.doi,
            "url": lead.url,
            "published_at": lead.published_at,
            "provider": lead.provider,
            "verification_status": lead.verification_status,
            "source_location": lead.source_location,
        }
        for lead in leads[:context.limits.max_items]
    ]
    return ToolResult(
        request_id=request.request_id, name=request.name, version="1.0",
        payload={"items": items, "count": len(items), "read_only": True},
        source_refs=[item["source_ref"] for item in items],
        data_space="verifiable_public",
        boundary_notes=["read-only", "verifiable_public", "server-verified-provider", "candidate-context-only"],
    )


def literature_spec() -> ToolSpec:
    return ToolSpec(
        name="literature.search", version="1.0",
        description="Search server-selected public literature and retain bounded provenance",
        read_only=True,
        input_schema={
            "type": "object", "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "from_year": {"type": "integer"}, "until_year": {"type": "integer"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                "verify": {"type": "boolean"},
            },
        },
        output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        allowed_roles=["master_student", "phd_student", "postdoc"],
        allowed_phases=["independent_analysis", "review_gate"],
        data_spaces=["real", "desensitized_real"],
        result_data_spaces=["verifiable_public"],
        result_limits={"max_items": 10, "max_bytes": 8192},
    )


def register_literature_tool(registry: ToolRegistry, search: GovernedLiteratureSearch, repository: LiteratureLeadRepository) -> None:
    registry.register(literature_spec(), lambda request, context: literature_search(request, context, search, repository))
