"""HTTP client for ForumMind's native Node Pi runtime."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from app.agent_runtime.pi_client import (
    PiAuthError,
    PiClientError,
    PiProtocolError,
    PiRawResult,
    PiTimeoutError,
    PiUnavailableError,
)
from app.agent_runtime.schemas import AgentInvocation, AgentResult


@dataclass(frozen=True)
class NativeSession:
    session_id: str
    cursor: int = 0
    session_scope: str = ""
    persisted: bool = False


class NativePiClient:
    """Call the internal Node service without exposing Pi transcripts."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 60.0,
        prompt_timeout: float | None = None,
        poll_interval: float = 0.05,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = max(timeout, 0.1)
        self.prompt_timeout = max(
            prompt_timeout if prompt_timeout is not None else self.timeout,
            0.1,
        )
        self.poll_interval = max(poll_interval, 0.0)
        self._client = client
        self.last_sessions: dict[str, NativeSession] = {}
        self.last_events: dict[str, list[dict[str, Any]]] = {}

    async def open_session(self, invocation: AgentInvocation) -> NativeSession:
        payload = await self._request("POST", "/v1/sessions", json=invocation.model_dump(mode="json"))
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise PiProtocolError("native session response lacks session_id")
        cursor = payload.get("cursor", 0)
        if not isinstance(cursor, int) or cursor < 0:
            raise PiProtocolError("native session cursor is invalid")
        return NativeSession(
            session_id=session_id,
            cursor=cursor,
            session_scope=str(payload.get("session_scope", "")),
            persisted=bool(payload.get("persisted", False)),
        )

    async def health(self) -> dict[str, Any]:
        """Read the runtime's secret-free provider health summary."""
        return await self._request("GET", "/health")

    async def check_provider(self) -> dict[str, Any]:
        """Run the runtime-owned provider check without sending a browser secret."""
        return await self._request("POST", "/v1/provider/check", json={})

    async def prompt(self, session_id: str, invocation: AgentInvocation) -> dict[str, Any]:
        return await self._request(
            "POST", f"/v1/sessions/{session_id}/prompts",
            json={"invocation": invocation.model_dump(mode="json")},
            request_timeout=self.prompt_timeout,
        )

    async def steer(self, session_id: str, message: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/sessions/{session_id}/steer", json={"message": message})

    async def follow_up(self, session_id: str, message: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/sessions/{session_id}/follow-up", json={"message": message})

    async def abort(self, session_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/sessions/{session_id}/abort", json={})

    async def events(self, session_id: str, after: int = 0) -> list[dict[str, Any]]:
        payload = await self._request("GET", f"/v1/sessions/{session_id}/events?after={max(after, 0)}")
        events = payload.get("events")
        if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
            raise PiProtocolError("native events response lacks events array")
        return [dict(event) for event in events]

    async def invoke(self, request: dict[str, object]) -> PiRawResult:
        """PiClient-compatible one-shot invocation used by the existing adapter."""
        try:
            invocation = AgentInvocation.model_validate(request)
        except Exception as exc:
            raise PiProtocolError(f"invalid native invocation: {exc}") from exc
        session = await self.open_session(invocation)
        self.last_sessions[invocation.agent_id] = session
        captured_events: list[dict[str, Any]] = []
        self.last_events[invocation.invocation_id] = captured_events
        response = await self.prompt(session.session_id, invocation)
        if response.get("accepted") is not True:
            error = response.get("error")
            error_code = response.get("error_code")
            reason = error if isinstance(error, str) and error.strip() else "native prompt was not accepted"
            if isinstance(error_code, str) and error_code.strip():
                reason = f"{reason} ({error_code})"
            raise PiProtocolError(f"native prompt rejected: {reason}")
        response_cursor = response.get("cursor", session.cursor)
        if not isinstance(response_cursor, int) or response_cursor < 0:
            raise PiProtocolError("native prompt cursor is invalid")
        # The prompt endpoint completes synchronously and returns its latest
        # cursor. Start from the pre-prompt cursor so the settled event is not
        # skipped when the response already includes it.
        cursor = session.cursor
        while True:
            for raw_event in await self.events(session.session_id, cursor):
                event_cursor = raw_event.get("cursor")
                if not isinstance(event_cursor, int) or event_cursor < 1:
                    raise PiProtocolError("native event cursor is invalid")
                if event_cursor <= cursor:
                    continue
                captured_events.append(dict(raw_event))
                cursor = event_cursor
                self.last_sessions[invocation.agent_id] = NativeSession(
                    session_id=session.session_id,
                    cursor=cursor,
                    session_scope=session.session_scope,
                    persisted=session.persisted,
                )
                event_type = raw_event.get("type")
                payload = raw_event.get("payload")
                if not isinstance(payload, dict):
                    raise PiProtocolError("native event payload must be an object")
                if event_type == "agent_settled":
                    return map_settled_result(invocation, payload)
                if event_type in {"agent_failed", "agent_aborted"}:
                    error = str(payload.get("error", event_type))
                    raw_error_code = payload.get("error_code")
                    error_code = (
                        raw_error_code.strip()
                        if isinstance(raw_error_code, str) and raw_error_code.strip()
                        else str(event_type)
                    )
                    return AgentResult(
                        agent_id=invocation.agent_id, status="error", content="",
                        error=error, error_code=error_code, warnings=[error],
                        data_space=invocation.data_space,
                    ).model_dump(mode="python")
            await asyncio.sleep(self.poll_interval)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        request_timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise PiUnavailableError("PI_RUNTIME_URL is not configured")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(trust_env=False)
        headers = {"X-ForumMind-Runtime-Token": self.token} if self.token else {}
        try:
            try:
                response = await client.request(
                    method,
                    self.base_url + path,
                    headers=headers,
                    timeout=self.timeout if request_timeout is None else request_timeout,
                    **kwargs,
                )
            except httpx.TimeoutException as exc:
                raise PiTimeoutError(f"native Pi request timeout: {exc}") from exc
            except httpx.HTTPError as exc:
                raise PiUnavailableError(f"native Pi request unavailable: {exc}") from exc
            if response.status_code in {401, 403}:
                raise PiAuthError(f"native Pi authentication failed: HTTP {response.status_code}")
            if response.status_code >= 500:
                raise PiUnavailableError(f"native Pi service unavailable: HTTP {response.status_code}")
            if response.status_code >= 400:
                raise PiProtocolError(f"native Pi rejected request: HTTP {response.status_code}")
            try:
                value = response.json()
            except (TypeError, ValueError) as exc:
                raise PiProtocolError("native Pi response is not valid JSON") from exc
            if not isinstance(value, dict):
                raise PiProtocolError("native Pi response must be a JSON object")
            return dict(value)
        finally:
            if owns_client:
                await client.aclose()


def map_settled_result(invocation: AgentInvocation, payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("result")
    if not isinstance(raw, Mapping):
        raise PiProtocolError("agent_settled event lacks result object")
    data = dict(raw)
    agent_id = data.get("agent_id", invocation.agent_id)
    data_space = data.get("data_space", invocation.data_space)
    if agent_id != invocation.agent_id:
        raise PiProtocolError("settled result agent_id mismatch")
    if data_space != invocation.data_space:
        raise PiProtocolError("settled result data_space mismatch")
    data.setdefault("status", "ok")
    data.setdefault("structured_output", {})
    data.setdefault("tool_calls", [])
    data.setdefault("runtime_state_ref", "")
    data.setdefault("warnings", [])
    data.setdefault("error", "")
    data.setdefault("error_code", "")
    data.setdefault("agent_id", invocation.agent_id)
    data.setdefault("data_space", invocation.data_space)
    try:
        return AgentResult.model_validate(data).model_dump(mode="python")
    except Exception as exc:
        raise PiProtocolError(f"settled result is invalid: {exc}") from exc
