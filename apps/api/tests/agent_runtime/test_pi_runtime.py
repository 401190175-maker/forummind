"""PiRuntime adapter tests (Task 4)."""

import asyncio
import inspect

from app.agent_runtime.pi_client import (
    PiAuthError,
    PiClient,
    PiProtocolError,
    PiTimeoutError,
    PiUnavailableError,
)
from app.agent_runtime.pi_runtime import PiRuntime
from app.agent_runtime.schemas import AgentInvocation


def _invocation() -> AgentInvocation:
    return AgentInvocation(
        run_id="run-1",
        group_chat_id="gc-1",
        cycle=1,
        phase="independent_analysis",
        agent_id="agent-ms-1",
        role="master_student",
        task="分析泡沫混凝土的孔结构机制",
        context={"capability": "文献与机制分析"},
        allowed_tools=[],
        output_contract="claim_four_fields",
        data_space="synthetic",
        safety_rules=["no_formal_memory_write"],
    )


class FakePiClient:
    def __init__(self, result: object | BaseException) -> None:
        self.result = result
        self.requests: list[dict[str, object]] = []

    async def invoke(self, request: dict[str, object]) -> object:
        self.requests.append(request)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_pi_runtime_maps_successful_result_and_request() -> None:
    client = FakePiClient(
        {
            "agent_id": "agent-ms-1",
            "content": "孔结构影响强度和吸水率。",
            "structured_output": {"boundary": "低密度样品"},
            "tool_calls": [],
            "runtime_state_ref": "pi-state-1",
            "warnings": ["候选观点"],
            "data_space": "synthetic",
        }
    )
    runtime = PiRuntime(client)

    result = asyncio.run(runtime.invoke(_invocation()))

    assert result.status == "ok"
    assert result.agent_id == "agent-ms-1"
    assert result.content == "孔结构影响强度和吸水率。"
    assert result.structured_output == {"boundary": "低密度样品"}
    assert result.runtime_state_ref == "pi-state-1"
    assert result.warnings == ["候选观点"]
    request = client.requests[0]
    assert request["run_id"] == "run-1"
    assert request["group_chat_id"] == "gc-1"
    assert request["agent_id"] == "agent-ms-1"
    assert request["role"] == "master_student"
    assert request["profile_version"] == ""
    assert request["agent_instruction"] is None
    assert request["task"] == "分析泡沫混凝土的孔结构机制"
    assert request["context"] == {"capability": "文献与机制分析"}
    assert request["output_contract"] == "claim_four_fields"


def test_pi_runtime_maps_pi_errors_to_error_result() -> None:
    runtime = PiRuntime(FakePiClient(PiTimeoutError("slow")))

    result = asyncio.run(runtime.invoke(_invocation()))

    assert result.status == "error"
    assert result.agent_id == "agent-ms-1"
    assert "slow" in result.error
    assert result.data_space == "synthetic"


def test_pi_runtime_maps_auth_error_to_error_result() -> None:
    runtime = PiRuntime(FakePiClient(PiAuthError("bad key")))

    result = asyncio.run(runtime.invoke(_invocation()))

    assert result.status == "error"
    assert "bad key" in result.error


def test_pi_runtime_preserves_unavailable_error_code() -> None:
    result = asyncio.run(PiRuntime(FakePiClient(PiUnavailableError("offline"))).invoke(_invocation()))

    assert result.status == "error"
    assert result.error_code == "pi_unavailable"


def test_pi_runtime_preserves_timeout_error_code() -> None:
    result = asyncio.run(PiRuntime(FakePiClient(PiTimeoutError("timeout"))).invoke(_invocation()))

    assert result.status == "error"
    assert result.error_code == "pi_timeout"


def test_pi_runtime_preserves_protocol_error_code() -> None:
    result = asyncio.run(
        PiRuntime(FakePiClient(PiProtocolError("bad envelope"))).invoke(_invocation())
    )

    assert result.status == "error"
    assert result.error_code == "pi_protocol"


def test_pi_runtime_preserves_native_error_result_code() -> None:
    result = asyncio.run(
        PiRuntime(
            FakePiClient(
                {
                    "agent_id": "agent-ms-1",
                    "status": "error",
                    "content": "",
                    "structured_output": {},
                    "tool_calls": [],
                    "runtime_state_ref": "session-1",
                    "warnings": ["native prompt failed"],
                    "error": "native prompt failed",
                    "error_code": "prompt_failed",
                    "data_space": "synthetic",
                }
            )
        ).invoke(_invocation())
    )

    assert result.status == "error"
    assert result.error_code == "prompt_failed"


def test_pi_runtime_rejects_non_object_result() -> None:
    runtime = PiRuntime(FakePiClient(["not", "object"]))

    result = asyncio.run(runtime.invoke(_invocation()))

    assert result.status == "error"
    assert "object" in result.error.lower()


def test_pi_runtime_has_no_business_side_effect_dependencies() -> None:
    source = inspect.getsource(__import__("app.agent_runtime.pi_runtime", fromlist=["*"]))

    for forbidden in ("fastapi", "orchestration", "memory", "runstore"):
        assert forbidden not in source.lower(), forbidden
