"""Read-only tool adapter for real, task-scoped document search."""

from __future__ import annotations

from typing import Any

from app.knowledge.schemas import SearchScope
from app.knowledge.search import KnowledgeSearch
from app.tools.errors import ToolArgumentsError, ToolScopeError
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest, ToolResult, ToolSpec

_AUTHORITY_ARGUMENTS = {"run_id", "group_chat_id", "agent_id", "task_id", "data_space"}


def _arguments(request: ToolRequest) -> dict[str, Any]:
    unknown = set(request.arguments) - {"query", "document_ids", "limit"} - _AUTHORITY_ARGUMENTS
    if unknown:
        raise ToolArgumentsError(f"unsupported arguments: {sorted(unknown)}")
    # Identity and authorization fields are deliberately ignored. They come from context.
    return {key: value for key, value in request.arguments.items() if key not in _AUTHORITY_ARGUMENTS}


def knowledge_search(request: ToolRequest, context, search: KnowledgeSearch) -> ToolResult:
    args = _arguments(request)
    query = args.get("query", "")
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ToolArgumentsError("query must be non-empty text of at most 500 characters")
    limit = args.get("limit", context.limits.max_items)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= context.limits.max_items:
        raise ToolArgumentsError(f"limit must be between 1 and {context.limits.max_items}")
    requested_documents = args.get("document_ids", list(context.allowed_document_ids))
    if not isinstance(requested_documents, list) or any(
        not isinstance(item, str) or not item.strip() for item in requested_documents
    ):
        raise ToolArgumentsError("document_ids must be a list of non-empty strings")
    requested_documents = [item.strip() for item in requested_documents]
    if any(document_id not in context.allowed_document_ids for document_id in requested_documents):
        raise ToolScopeError("document_scope_denied")
    scope = SearchScope(
        group_chat_id=context.group_chat_id,
        task_id=context.task_id,
        data_space=context.data_space,
        allowed_document_ids=requested_documents,
    )
    hits = search.search(scope, query, limit)
    return ToolResult(
        request_id=request.request_id,
        name=request.name,
        version="1.0",
        payload={
            "items": [hit.model_dump(mode="json") for hit in hits],
            "count": len(hits),
            "read_only": True,
        },
        source_refs=[hit.chunk_id for hit in hits],
        data_space=context.data_space,
        boundary_notes=["read-only", context.data_space, "user-uploaded-source", "candidate-context-only"],
    )


def knowledge_spec() -> ToolSpec:
    return ToolSpec(
        name="knowledge.search",
        version="1.0",
        description="Search indexed documents authorized for the current research task",
        read_only=True,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "document_ids": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
        output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        allowed_roles=["master_student", "phd_student", "postdoc"],
        allowed_phases=["independent_analysis", "review_gate"],
        data_spaces=["real", "desensitized_real"],
        result_limits={"max_items": 10, "max_bytes": 8192},
    )


def register_knowledge_tool(registry: ToolRegistry, search: KnowledgeSearch) -> None:
    registry.register(knowledge_spec(), lambda request, context: knowledge_search(request, context, search))
