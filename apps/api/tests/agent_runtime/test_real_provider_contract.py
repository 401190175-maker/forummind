import asyncio

import pytest

from app.agent_runtime.native_pi_client import NativePiClient
from app.agent_runtime.pi_client import PiAuthError


class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.calls = []
        self.responses = list(responses)

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_native_provider_check_returns_health_without_secret():
    http = FakeClient([
        Response(200, {
            "configured": True,
            "provider": "openai-compatible",
            "model": "research-model",
            "reachable": True,
            "latency_ms": 12,
            "error_code": "",
        })
    ])

    result = asyncio.run(
        NativePiClient("http://pi-runtime", "runtime-secret", client=http).check_provider()
    )

    assert result["reachable"] is True
    assert result["model"] == "research-model"
    assert "runtime-secret" not in str(result)
    assert http.calls[0][0:2] == ("POST", "http://pi-runtime/v1/provider/check")


def test_native_provider_check_maps_authentication_failure():
    http = FakeClient([Response(401, {"error": {"code": "provider_auth"}})])

    with pytest.raises(PiAuthError):
        asyncio.run(
            NativePiClient("http://pi-runtime", "runtime-secret", client=http).check_provider()
        )
