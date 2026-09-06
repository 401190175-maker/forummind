"""MockRuntime 测试（Agent Runtime Adapter 前置 Task 5）。"""

import asyncio
import inspect

from app.agent_runtime import AgentInvocation, AgentResult, MockRuntime


def _invocation(agent_id: str = "agent-ms-1") -> AgentInvocation:
    return AgentInvocation(
        run_id="run-1",
        group_chat_id="gc-1",
        cycle=1,
        phase="independent_analysis",
        agent_id=agent_id,
        role="master_student",
        task="分析候选机制",
    )


def test_mock_runtime_returns_preset_result_and_records_invocation() -> None:
    preset = AgentResult(agent_id="agent-ms-1", status="ok", content="候选结论")
    runtime = MockRuntime(result=preset)

    result = asyncio.run(runtime.invoke(_invocation()))

    assert result is preset
    assert runtime.invocations[0].run_id == "run-1"
    assert runtime.invocations[0].phase == "independent_analysis"


def test_mock_runtime_uses_result_factory() -> None:
    def make_result(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="fallback",
            content=f"{invocation.agent_id}: fallback",
        )

    runtime = MockRuntime(result_factory=make_result)
    result = asyncio.run(runtime.invoke(_invocation("agent-ms-2")))

    assert result.agent_id == "agent-ms-2"
    assert result.status == "fallback"
    assert result.content == "agent-ms-2: fallback"
    assert len(runtime.invocations) == 1


def test_mock_runtime_can_simulate_error_status() -> None:
    runtime = MockRuntime(
        result=AgentResult(
            agent_id="agent-ms-1",
            status="error",
            content="",
            error="simulated runtime failure",
        )
    )

    result = asyncio.run(runtime.invoke(_invocation()))

    assert result.status == "error"
    assert "simulated" in result.error


def test_mock_runtime_default_result_is_ok_candidate() -> None:
    result = asyncio.run(MockRuntime().invoke(_invocation()))
    assert result.agent_id == "agent-ms-1"
    assert result.status == "ok"
    assert result.content


def test_mock_runtime_does_not_import_external_runtime_dependencies() -> None:
    import app.agent_runtime.mock_runtime as module

    source = inspect.getsource(module)
    for forbidden in ("app.llm", "scenario", "memory", "fastapi", "open("):
        assert forbidden not in source, forbidden
