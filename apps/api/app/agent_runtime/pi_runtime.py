"""Pi-backed implementation of the Agent Runtime protocol."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import time

from app.agent_runtime.pi_client import (
    PiAuthError,
    PiClient,
    PiClientError,
    PiProtocolError,
    PiTimeoutError,
    PiUnavailableError,
    build_tool_follow_up,
    normalize_pi_response,
)
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.tools.context import ToolExecutionContext
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest


class PiRuntime:
    """Adapt one ForumMind invocation to one Pi client call."""

    def __init__(
        self,
        client: PiClient,
        model: str | ToolRegistry = "",
        tool_registry: ToolRegistry | Callable[[AgentInvocation], ToolExecutionContext] | None = None,
        context_factory: Callable[[AgentInvocation], ToolExecutionContext] | None = None,
    ) -> None:
        self._client = client
        # Preserve the pre-model constructor form: PiRuntime(client, registry, context_factory).
        if isinstance(model, ToolRegistry):
            legacy_context_factory = tool_registry if callable(tool_registry) else None
            self._model = ""
            self._tool_registry = model
            self._context_factory = context_factory or legacy_context_factory
        else:
            self._model = model
            self._tool_registry = tool_registry if isinstance(tool_registry, ToolRegistry) else None
            self._context_factory = context_factory

    async def invoke(self, invocation: AgentInvocation) -> AgentResult:
        """Run one candidate-producing Pi invocation without business side effects."""
        request = invocation.model_dump(mode="json")
        if self._model:
            request["model"] = self._model
        context = None
        if self._tool_registry is not None and self._context_factory is not None and invocation.allowed_tools:
            try:
                context = self._context_factory(invocation)
                allowed_tools = set(invocation.allowed_tools)
                request["tool_specs"] = [
                    spec.model_dump(mode="json")
                    for spec in self._tool_registry.list_specs(context)
                    if spec.name in allowed_tools
                ]
            except Exception as exc:
                return self._error_result(invocation, f"tool context error: {exc}")
        calls = []
        started = time.monotonic()
        seen_requests: set[str] = set()
        max_calls = context.limits.max_calls if context is not None else 0
        while True:
            if context is not None and time.monotonic() - started > context.limits.deadline_seconds:
                return self._error_result(invocation, "tool loop limit exceeded", calls)
            try:
                raw_result = await self._client.invoke(request)
                envelope = normalize_pi_response(raw_result)
            except PiClientError as exc:
                return self._error_result(
                    invocation, str(exc), calls, self._error_code(exc)
                )
            except Exception as exc:  # Keep a transport implementation from crashing the run.
                return self._error_result(
                    invocation, f"Pi runtime error: {exc}", calls, "pi_runtime"
                )

            if envelope.get("type") != "tool_request":
                return self._map_final(invocation, envelope, calls)
            if context is None or self._tool_registry is None:
                return self._error_result(
                    invocation,
                    "tool request received while tools are disabled",
                    calls,
                    "pi_protocol",
                )
            request_id = envelope["request_id"]
            if request_id in seen_requests:
                duplicate = ToolRequest(
                    request_id=request_id, name=envelope["name"], arguments=envelope["arguments"],
                    input_refs=envelope.get("input_refs", []), data_space=envelope.get("data_space", invocation.data_space),
                )
                duplicate_result = self._tool_registry.limit(duplicate, context, "duplicate_request")
                calls.append(self._tool_registry.audit(invocation.run_id)[-1].model_dump(mode="json"))
                return self._error_result(
                    invocation, "duplicate tool request", calls, "pi_protocol"
                )
            seen_requests.add(request_id)
            tool_request = ToolRequest(
                request_id=request_id, name=envelope["name"], arguments=envelope["arguments"],
                input_refs=envelope.get("input_refs", []), data_space=envelope.get("data_space", invocation.data_space),
            )
            if tool_request.name not in invocation.allowed_tools:
                return self._error_result(
                    invocation,
                    f"tool request is outside invocation allowlist: {tool_request.name}",
                    calls,
                    "pi_tool_not_allowed",
                )
            if len(calls) >= max_calls:
                result = self._tool_registry.limit(tool_request, context)
                calls.append(self._tool_registry.audit(invocation.run_id)[-1].model_dump(mode="json"))
                return self._error_result(
                    invocation, "tool loop limit exceeded", calls, "pi_tool_limit"
                )
            result = self._tool_registry.execute(tool_request, context)
            audit_records = self._tool_registry.audit(invocation.run_id)
            if audit_records:
                calls.append(audit_records[-1].model_dump(mode="json"))
            request = build_tool_follow_up(request, result)

    @property
    def last_sessions(self) -> dict[str, object]:
        """Expose native session references without exposing transcript content."""
        value = getattr(self._client, "last_sessions", {})
        return dict(value) if isinstance(value, dict) else {}

    @property
    def last_events(self) -> dict[str, list[dict]]:
        """Expose bounded normalized runtime events for server-side projection."""
        value = getattr(self._client, "last_events", {})
        return {
            str(key): [dict(event) for event in events]
            for key, events in value.items()
            if isinstance(events, list) and all(isinstance(event, dict) for event in events)
        } if isinstance(value, dict) else {}

    def _map_final(self, invocation: AgentInvocation, raw_result: Mapping[str, object], calls: list[dict]) -> AgentResult:
        """Map the normalized final envelope using the P1 response contract."""
        content = raw_result.get("content", "")
        if not isinstance(content, str):
            return self._error_result(
                invocation, "Pi response content must be text", calls, "pi_protocol"
            )
        status = raw_result.get("status", "ok")
        if status == "error":
            error = raw_result.get("error") or content or "Pi returned an error"
            raw_error_code = raw_result.get("error_code")
            error_code = (
                raw_error_code.strip()
                if isinstance(raw_error_code, str) and raw_error_code.strip()
                else "pi_error"
            )
            return self._error_result(invocation, str(error), calls, error_code)
        structured_output = raw_result.get("structured_output", {})
        legacy_calls = raw_result.get("tool_calls", calls)
        warnings = raw_result.get("warnings", [])
        runtime_state_ref = raw_result.get("runtime_state_ref", "")
        data_space = raw_result.get("data_space", invocation.data_space)
        agent_id = raw_result.get("agent_id", invocation.agent_id)
        if not isinstance(structured_output, dict):
            return self._error_result(
                invocation,
                "Pi structured_output must be an object",
                calls,
                "pi_protocol",
            )
        if not isinstance(legacy_calls, list):
            return self._error_result(
                invocation, "Pi tool_calls must be a list", calls, "pi_protocol"
            )
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            return self._error_result(
                invocation,
                "Pi warnings must be a list of strings",
                calls,
                "pi_protocol",
            )
        if not isinstance(runtime_state_ref, str) or not isinstance(data_space, str) or not isinstance(agent_id, str):
            return self._error_result(
                invocation,
                "Pi response field has invalid type",
                calls,
                "pi_protocol",
            )
        return AgentResult(
            agent_id=agent_id, status="ok", content=content,
            structured_output=structured_output, tool_calls=legacy_calls,
            runtime_state_ref=runtime_state_ref, warnings=warnings, data_space=data_space,
        )

    @staticmethod
    def _error_result(
        invocation: AgentInvocation,
        message: str,
        tool_calls: list[dict] | None = None,
        error_code: str = "pi_runtime",
    ) -> AgentResult:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="error",
            content="",
            tool_calls=tool_calls or [],
            error=message,
            error_code=error_code,
            warnings=[message],
            data_space=invocation.data_space,
        )

    @staticmethod
    def _error_code(error: PiClientError) -> str:
        if isinstance(error, PiUnavailableError):
            return "pi_unavailable"
        if isinstance(error, PiTimeoutError):
            return "pi_timeout"
        if isinstance(error, PiProtocolError):
            return "pi_protocol"
        if isinstance(error, PiAuthError):
            return "pi_auth"
        return "pi_client"
