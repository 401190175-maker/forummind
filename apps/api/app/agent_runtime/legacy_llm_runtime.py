"""Legacy LLM Runtime：包装现有 `app.llm.chat()`（design.md §2.6，tasks.md Task 19）。

- `chat()` 成功时返回 `AgentResult(status="ok")`。
- `LLMError` 时返回 `AgentResult(status="error")`（含可读 warning）。
- runtime 不写 RunStep、不写 Memory；写入仍由 orchestration 控制。
- 不改变现有 live 行为：等价于 `run_live()` 直接调用 `chat()` 的语义。
"""

from __future__ import annotations

from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.llm.provider import LLMError, chat


class LegacyLLMRuntime:
    """把 `app.llm.chat()` 包装为 runtime adapter（Pi 接入 Phase 1）。"""

    async def invoke(self, invocation: AgentInvocation) -> AgentResult:
        """调用 legacy LLM provider；失败返回 `AgentResult(status="error")`，不抛出。"""
        messages = []
        if invocation.agent_instruction is not None:
            messages.append(
                {"role": "system", "content": invocation.agent_instruction.render()}
            )
        messages.append({"role": "user", "content": invocation.task})
        try:
            text = await chat(messages)
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content=text,
                data_space=invocation.data_space,
            )
        except LLMError as exc:
            return AgentResult(
                agent_id=invocation.agent_id,
                status="error",
                content="",
                warnings=[str(exc)],
                error=str(exc),
                data_space=invocation.data_space,
            )
