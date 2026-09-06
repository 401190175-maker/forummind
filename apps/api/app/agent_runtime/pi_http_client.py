"""HTTP transport for the Pi Agent Runtime client."""

from __future__ import annotations

import json

import httpx

from app.agent_runtime.pi_client import (
    PiAuthError,
    PiProtocolError,
    PiTimeoutError,
    PiUnavailableError,
    PiRawResult,
    PiRequest,
)


class HttpPiClient:
    """Call an internal Pi Sidecar endpoint for one Agent invocation."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        protocol: str = "pi",
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.strip()
        self.api_key = api_key
        self.protocol = protocol.strip().lower() or "pi"
        self.timeout = timeout
        self._client = client

    async def invoke(self, request: PiRequest) -> PiRawResult:
        """Post one Pi request and return a JSON object result."""
        if not self.base_url:
            raise PiUnavailableError("PI_BASE_URL is not configured")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient()
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        endpoint = self._endpoint()
        payload = self._openai_payload(request) if self.protocol == "openai_compatible" else request
        try:
            try:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as exc:
                raise PiTimeoutError(f"Pi request timeout: {exc}") from exc
            except httpx.HTTPError as exc:
                raise PiUnavailableError(f"Pi request unavailable: {exc}") from exc

            if response.status_code in {401, 403}:
                raise PiAuthError(f"Pi authentication failed: HTTP {response.status_code}")
            if response.status_code >= 500:
                raise PiUnavailableError(f"Pi service unavailable: HTTP {response.status_code}")
            if response.status_code >= 400:
                raise PiProtocolError(f"Pi rejected request: HTTP {response.status_code}")

            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise PiProtocolError("Pi response is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise PiProtocolError("Pi response must be a JSON object")
            if self.protocol == "openai_compatible":
                return self._normalize_openai_response(payload, request)
            return payload
        finally:
            if owns_client:
                await client.aclose()

    def _endpoint(self) -> str:
        if self.protocol != "openai_compatible":
            return self.base_url
        suffix = "/chat/completions"
        return self.base_url if self.base_url.rstrip("/").endswith(suffix) else self.base_url.rstrip("/") + suffix

    @staticmethod
    def _openai_payload(request: PiRequest) -> dict[str, object]:
        instruction = request.get("agent_instruction")
        messages: list[dict[str, str]] = []
        if instruction is not None:
            rendered = instruction if isinstance(instruction, str) else json.dumps(
                instruction, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            messages.append({"role": "system", "content": "ForumMind AgentInstruction\n" + rendered})
        user_payload = {
            "task": request.get("task", ""),
            "context": request.get("context", {}),
            "input_refs": request.get("input_refs", []),
            "tool_results": request.get("tool_results", []),
        }
        messages.append({
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
        })
        return {
            "model": request.get("model", ""),
            "messages": messages,
            "temperature": 0.2,
        }

    @staticmethod
    def _normalize_openai_response(
        payload: dict[str, object], request: PiRequest
    ) -> dict[str, object]:
        try:
            choices = payload["choices"]
            message = choices[0]["message"]  # type: ignore[index]
            content = message["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise PiProtocolError("OpenAI-compatible response lacks choices.message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise PiProtocolError("OpenAI-compatible response content must be non-empty text")
        structured_output: dict[str, object] = {}
        candidate = content.strip()
        if candidate.startswith("```"):
            candidate = candidate.removeprefix("```").removeprefix("json").removesuffix("```").strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            nested = parsed.get("structured_output")
            structured_output = nested if isinstance(nested, dict) else parsed
        return {
            "type": "final",
            "agent_id": request.get("agent_id", ""),
            "content": content,
            "structured_output": structured_output,
            "tool_calls": [],
            "data_space": request.get("data_space", "synthetic"),
        }
