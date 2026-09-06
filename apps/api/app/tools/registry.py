"""The sole dispatch and audit boundary for ForumMind tools."""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from typing import Any

from app.tools.audit import AuditRecorder
from app.tools.context import ToolExecutionContext
from app.tools.errors import ToolArgumentsError, ToolProviderUnavailable, ToolScopeError
from app.tools.policy import authorize_tool, resolve_allowed_tools
from app.tools.schemas import ToolCallRecord, ToolPolicyDecision, ToolRequest, ToolResult, ToolSpec

ToolHandler = Callable[[ToolRequest, ToolExecutionContext], ToolResult]


class ToolRegistry:
    def __init__(self, audit_recorder: AuditRecorder | None = None) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._audit = audit_recorder or AuditRecorder()
        self._completed_requests: set[tuple[str, str]] = set()

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if spec.name in self._specs:
            raise ValueError(f"tool {spec.name!r} is already registered")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def list_specs(self, context: ToolExecutionContext) -> list[ToolSpec]:
        allowed = set(resolve_allowed_tools(context).allowed_tools)
        return [spec.model_copy(deep=True) for name, spec in self._specs.items() if name in allowed]

    def authorize(self, request: ToolRequest, context: ToolExecutionContext) -> ToolPolicyDecision:
        return authorize_tool(request, context, self._specs.values())

    def execute(self, request: ToolRequest, context: ToolExecutionContext) -> ToolResult:
        started = time.time()
        spec = self._specs.get(request.name)
        version = spec.version if spec else "unknown"
        request_key = (context.run_id, request.request_id)
        if request_key in self._completed_requests:
            return self.limit(request, context, "duplicate_request")
        self._completed_requests.add(request_key)
        decision = self.authorize(request, context)
        if not decision.allowed:
            result = ToolResult(
                request_id=request.request_id, name=request.name, version=version,
                status="denied", error_code=decision.reason, data_space=request.data_space,
                boundary_notes=self._boundary_notes(context, "candidate-context-only"),
            )
            self._record(request, context, version, "rejected", result, started, decision.reason)
            return result

        handler = self._handlers[request.name]
        try:
            result = handler(request, context)
            if not isinstance(result, ToolResult):
                raise TypeError("tool handler must return ToolResult")
            if result.request_id != request.request_id or result.name != request.name:
                raise ValueError("tool result identity does not match request")
            if result.version != spec.version:
                raise ValueError("tool result version does not match spec")
            if (
                result.data_space not in (spec.result_data_spaces or spec.data_spaces)
                or result.data_space not in context.allowed_source_data_spaces
            ):
                return self._error(request, context, spec.version, "data_space_mismatch", started)
            max_bytes = min(
                context.limits.max_result_bytes,
                spec.result_limits.get("max_bytes", context.limits.max_result_bytes),
            )
            result_size = len(json.dumps(result.payload, ensure_ascii=False, default=str).encode("utf-8"))
            if result_size > max_bytes:
                result = ToolResult(
                    request_id=request.request_id, name=request.name, version=spec.version,
                    status="limit_exceeded", payload={"truncated": True, "size_bytes": result_size},
                    source_refs=list(result.source_refs), error_code="result_size_exceeded",
                    data_space=context.data_space,
                    boundary_notes=self._boundary_notes(context, "result truncated by server limit"),
                )
                self._record(request, context, spec.version, "limit_exceeded", result, started, result.error_code)
                return result
            self._record(request, context, spec.version, "success", result, started, None)
            return result
        except ToolArgumentsError as exc:
            result = self._error(request, context, version, "invalid_arguments", started, str(exc))
            return result
        except ToolScopeError as exc:
            scope_code = str(exc).strip()
            if scope_code not in {"document_scope_denied", "dataset_scope_denied"}:
                scope_code = "scope_denied"
            result = self._error(request, context, version, scope_code, started, str(exc))
            return result
        except ToolProviderUnavailable:
            return self._error(request, context, version, "provider_unavailable", started)
        except Exception as exc:
            result = self._error(request, context, version, "tool_error", started, str(exc))
            return result

    def audit(self, run_id: str) -> list[ToolCallRecord]:
        return self._audit.list_for_run(run_id)

    def limit(self, request: ToolRequest, context: ToolExecutionContext, reason: str = "call_limit_exceeded") -> ToolResult:
        started = time.time()
        spec = self._specs.get(request.name)
        version = spec.version if spec else "unknown"
        result = ToolResult(
            request_id=request.request_id, name=request.name,
            version=version,
            status="limit_exceeded", error_code=reason, data_space=context.data_space,
            boundary_notes=self._boundary_notes(context, "tool budget exhausted"),
        )
        self._record(request, context, result.version, "limit_exceeded", result, started, reason)
        return result

    @staticmethod
    def _argument_summary(arguments: dict[str, Any]) -> dict[str, Any]:
        keys = sorted(str(key) for key in arguments)[:32]
        digest = hashlib.sha256(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest()
        return {"keys": keys, "count": len(arguments), "sha256": digest}

    def _record(
        self, request: ToolRequest, context: ToolExecutionContext, version: str,
        status: str, result: ToolResult, started: float, error_code: str | None,
    ) -> None:
        record = ToolCallRecord(
            record_id=f"audit-{request.request_id}-{int(started * 1000000)}",
            request_id=request.request_id, run_id=context.run_id, group_chat_id=context.group_chat_id,
            cycle=context.cycle, phase=context.phase, agent_id=context.agent_id, role=context.role,
            runtime=context.runtime_name, tool_name=request.name, tool_version=version,
            authorization="allowed" if status != "rejected" else "denied",
            status=status, argument_summary=self._argument_summary(request.arguments),
            source_refs=list(result.source_refs),
            result_summary={"status": result.status, "keys": sorted(result.payload)[:32],
                            "items": len(result.payload.get("items", [])) if isinstance(result.payload.get("items"), list) else 0},
            requested_data_space=request.data_space, returned_data_space=result.data_space,
            policy_version="p2-v1", error_code=error_code or result.error_code,
            error_message=(error_code or result.error_code or "")[:240], started_at=started,
            duration_ms=max((time.time() - started) * 1000, 0),
        )
        self._audit.append(record)

    def _error(
        self, request: ToolRequest, context: ToolExecutionContext, version: str,
        error_code: str, started: float, detail: str = "",
    ) -> ToolResult:
        result = ToolResult(
            request_id=request.request_id, name=request.name, version=version,
            status="error", error_code=error_code, data_space=context.data_space,
            boundary_notes=self._boundary_notes(context, "candidate-context-only"),
        )
        self._record(request, context, version, "error", result, started, error_code)
        return result

    @staticmethod
    def _boundary_notes(context: ToolExecutionContext, *notes: str) -> list[str]:
        return ["read-only", context.data_space, *notes]


def build_synthetic_registry(audit_recorder: AuditRecorder | None = None) -> ToolRegistry:
    """Build a fresh registry with only the three P2 synthetic tools."""
    from app.tools.synthetic import (
        register_experiment_tool,
        register_literature_tool,
        register_memory_tool,
    )

    registry = ToolRegistry(audit_recorder)
    register_memory_tool(registry)
    register_literature_tool(registry)
    register_experiment_tool(registry)
    return registry


def build_real_registry(
    knowledge_search,
    audit_recorder: AuditRecorder | None = None,
    experiment_repository=None,
    literature_search=None,
    literature_repository=None,
) -> ToolRegistry:
    """Build a Live registry containing only the task-scoped real search tool."""
    from app.tools.knowledge import register_knowledge_tool

    registry = ToolRegistry(audit_recorder)
    register_knowledge_tool(registry, knowledge_search)
    if experiment_repository is not None:
        from app.tools.experiment import register_experiment_tool
        register_experiment_tool(registry, experiment_repository)
    if literature_search is not None and literature_repository is not None:
        from app.tools.literature import register_literature_tool
        register_literature_tool(registry, literature_search, literature_repository)
    return registry


build_live_registry = build_real_registry
