"""Testing runtime for deterministic AgentRuntime invocations."""

from __future__ import annotations

from collections.abc import Callable

from app.agent_runtime.schemas import AgentInvocation, AgentResult

ResultFactory = Callable[[AgentInvocation], AgentResult]


class MockRuntime:
    """Deterministic runtime used by tests."""

    def __init__(
        self,
        result: AgentResult | None = None,
        result_factory: ResultFactory | None = None,
    ) -> None:
        self._result = result
        self._result_factory = result_factory
        self.invocations: list[AgentInvocation] = []

    async def invoke(self, invocation: AgentInvocation) -> AgentResult:
        self.invocations.append(invocation)
        if self._result_factory is not None:
            return self._result_factory(invocation)
        if self._result is not None:
            return self._result
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="mock runtime candidate",
            data_space=invocation.data_space,
        )
