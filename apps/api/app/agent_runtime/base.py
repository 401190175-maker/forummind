"""Agent Runtime 协议（design.md §2.6，tasks.md Task 19）。

`AgentRuntime` 是 orchestration 调用单个 Agent 的统一接口：
replay、legacy LLM、Pi runtime、mock runtime 都实现同一形状。
runtime 只返回候选结果，不负责阶段推进、审查门、冻结、
Memory 正式写入或 PI 裁决。
"""

from __future__ import annotations

from typing import Protocol

from app.agent_runtime.schemas import AgentInvocation, AgentResult


class AgentRuntime(Protocol):
    """单个 Agent 执行接口：`invoke(invocation) -> AgentResult`。"""

    async def invoke(self, invocation: AgentInvocation) -> AgentResult:
        """执行一次 Agent 调用并返回候选结果（不写 RunStep / Memory）。"""
        ...
