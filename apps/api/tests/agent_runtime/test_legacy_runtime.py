"""Legacy LLM Runtime Adapter 测试（tasks.md Task 19）。"""
import asyncio
import inspect

from app.agent_runtime.base import AgentRuntime
from app.agent_runtime.legacy_llm_runtime import LegacyLLMRuntime
from app.agent_runtime.schemas import AgentInvocation
from app.llm.provider import LLMError


def _invocation(task: str = "分析强度下降机制") -> AgentInvocation:
    return AgentInvocation(
        agent_id="agent-ms-1",
        role="master_student",
        task=task,
        data_space="synthetic",
    )


def test_runtime_protocol_defined() -> None:
    """runtime 协议或抽象接口存在，invoke 返回 AgentResult。"""
    assert inspect.isclass(AgentRuntime)
    signature = inspect.signature(AgentRuntime.invoke)
    return_type = signature.return_annotation
    assert "AgentResult" in str(return_type)


def test_legacy_runtime_satisfies_protocol() -> None:
    """LegacyLLMRuntime 提供 async invoke(invocation)。"""
    runtime = LegacyLLMRuntime()
    assert hasattr(runtime, "invoke")
    assert inspect.iscoroutinefunction(runtime.invoke)
    signature = inspect.signature(runtime.invoke)
    assert "invocation" in signature.parameters


def test_invoke_success_returns_ok(monkeypatch) -> None:
    async def fake_chat(messages, **kwargs):
        assert messages[0]["role"] == "user"
        return "LLM 生成的判断"

    from app.agent_runtime import legacy_llm_runtime as module

    monkeypatch.setattr(module, "chat", fake_chat)
    result = asyncio.run(LegacyLLMRuntime().invoke(_invocation()))
    assert result.agent_id == "agent-ms-1"
    assert result.status == "ok"
    assert result.content == "LLM 生成的判断"
    assert result.error == ""
    assert result.tool_calls == []
    assert result.runtime_state_ref == ""
    assert result.warnings == []
    assert result.data_space == "synthetic"


def test_invoke_llm_error_returns_error(monkeypatch) -> None:
    async def boom(messages, **kwargs):
        raise LLMError("LLM_API_KEY 未配置")

    from app.agent_runtime import legacy_llm_runtime as module

    monkeypatch.setattr(module, "chat", boom)
    result = asyncio.run(LegacyLLMRuntime().invoke(_invocation()))
    assert result.agent_id == "agent-ms-1"
    assert result.status == "error"
    assert result.content == ""
    assert "LLM_API_KEY" in result.error
    assert len(result.warnings) == 1
    assert "LLM_API_KEY" in result.warnings[0]


def test_runtime_does_not_write_run_step_or_memory() -> None:
    """runtime 不写 RunStep、不写 Memory（导入面与调用面检查）。"""
    import inspect as _inspect

    module = __import__(
        "app.agent_runtime.legacy_llm_runtime", fromlist=["LegacyLLMRuntime"]
    )
    source = _inspect.getsource(module)
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    for forbidden in ("orchestration", "memory", "run_store", "RunStep", "MemoryTimeline"):
        assert not any(forbidden in line for line in import_lines), forbidden
    # 调用面：不出现对 RunState/step/memory 的写入模式
    for forbidden in ("state.steps", "memory.append", ".steps.append"):
        assert forbidden not in source, forbidden
