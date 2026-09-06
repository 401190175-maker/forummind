"""HTTP Pi client tests (Task 3)."""

import asyncio

import httpx

from app.agent_runtime.pi_client import (
    PiAuthError,
    PiProtocolError,
    PiTimeoutError,
    PiUnavailableError,
)
from app.agent_runtime.pi_http_client import HttpPiClient


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class FakeAsyncClient:
    def __init__(self, response: FakeResponse | BaseException) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.closed = False

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def aclose(self) -> None:
        self.closed = True


def test_http_pi_client_posts_request_and_returns_json() -> None:
    http_client = FakeAsyncClient(FakeResponse(200, {"content": "候选观点"}))
    client = HttpPiClient(
        base_url="http://pi-sidecar/invoke",
        api_key="pi-secret",
        client=http_client,
    )

    result = asyncio.run(client.invoke({"task": "分析"}))

    assert result == {"content": "候选观点"}
    assert http_client.calls == [
        {
            "url": "http://pi-sidecar/invoke",
            "headers": {"Authorization": "Bearer pi-secret"},
            "json": {"task": "分析"},
            "timeout": 60.0,
        }
    ]
    assert http_client.closed is False


def test_http_pi_client_rejects_missing_base_url() -> None:
    client = HttpPiClient(base_url="", api_key="pi-secret")

    try:
        asyncio.run(client.invoke({"task": "分析"}))
    except PiUnavailableError as exc:
        assert "PI_BASE_URL" in str(exc)
    else:
        raise AssertionError("missing base URL should be rejected")


def test_http_pi_client_maps_timeout() -> None:
    http_client = FakeAsyncClient(httpx.ReadTimeout("slow"))
    client = HttpPiClient(
        base_url="http://pi-sidecar/invoke",
        api_key="pi-secret",
        client=http_client,
    )

    try:
        asyncio.run(client.invoke({"task": "分析"}))
    except PiTimeoutError as exc:
        assert "timeout" in str(exc).lower()
    else:
        raise AssertionError("timeout should be mapped")


def test_http_pi_client_maps_auth_failure() -> None:
    client = HttpPiClient(
        base_url="http://pi-sidecar/invoke",
        api_key="pi-secret",
        client=FakeAsyncClient(FakeResponse(401, {"error": "unauthorized"})),
    )

    try:
        asyncio.run(client.invoke({"task": "分析"}))
    except PiAuthError as exc:
        assert "401" in str(exc)
    else:
        raise AssertionError("401 should be mapped")


def test_http_pi_client_rejects_malformed_response() -> None:
    client = HttpPiClient(
        base_url="http://pi-sidecar/invoke",
        api_key="pi-secret",
        client=FakeAsyncClient(FakeResponse(200, ValueError("invalid json"))),
    )

    try:
        asyncio.run(client.invoke({"task": "分析"}))
    except PiProtocolError as exc:
        assert "response" in str(exc).lower()
    else:
        raise AssertionError("malformed response should be rejected")
