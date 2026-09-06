"""Pi client contract tests (Task 1)."""

import inspect
import asyncio

from app.agent_runtime.pi_client import (
    PiAuthError,
    PiClient,
    PiClientError,
    PiProtocolError,
    PiTimeoutError,
    PiUnavailableError,
)


class FakePiClient:
    async def invoke(self, request: dict[str, object]) -> dict[str, object]:
        return {"content": request["task"]}


def test_fake_client_can_implement_pi_client_contract() -> None:
    client: PiClient = FakePiClient()

    result = asyncio.run(client.invoke({"task": "分析泡沫混凝土"}))

    assert result == {"content": "分析泡沫混凝土"}


def test_pi_client_errors_share_common_base() -> None:
    assert issubclass(PiTimeoutError, PiClientError)
    assert issubclass(PiAuthError, PiClientError)
    assert issubclass(PiProtocolError, PiClientError)
    assert issubclass(PiUnavailableError, PiClientError)


def test_pi_client_contract_has_no_business_dependencies() -> None:
    source = inspect.getsource(__import__("app.agent_runtime.pi_client", fromlist=["*"]))

    for forbidden in ("fastapi", "orchestration", "memory", "app.llm", "httpx"):
        assert forbidden not in source.lower(), forbidden
