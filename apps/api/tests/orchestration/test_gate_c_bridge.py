"""P2-owned bridge contracts for the Gate C shared entry points."""

from __future__ import annotations

import asyncio

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.domain.schemas import AgentProfile
from app.orchestration import engine
from app.orchestration.run_store import RunStore
from app.storage.sqlite_store import SQLiteStore
from app.tasks.schemas import ResearchTask


def _agents() -> list[AgentProfile]:
    return [
        AgentProfile(
            agent_id=f"agent-{index}",
            name=f"分析 Agent {index}",
            role="master_student",
            primary_ability="资料分析",
            allowed_data_spaces=["desensitized_real"],
            allowed_tools=["knowledge.search"],
        )
        for index in range(1, 4)
    ]


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task-gate-c",
        group_chat_id="gc-gate-c",
        title="Gate C task",
        question="资料支持什么判断？",
        document_ids=[],
        data_space="desensitized_real",
        status="ready",
        created_at=1.0,
        updated_at=1.0,
    )


def _result(invocation: AgentInvocation) -> AgentResult:
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=f"{invocation.agent_id} candidate",
        structured_output={
            "claim": f"{invocation.agent_id} claim",
            "evidence_refs": ["chunk-1"],
            "reasoning_summary": "scoped evidence",
            "uncertainty": "limited sample",
            "next_action": "collect more evidence",
        },
        data_space=invocation.data_space,
    )


def test_task_bridge_projects_task_materials_through_optional_meeting_service() -> None:
    class MeetingProjection:
        def __init__(self) -> None:
            self.states = []

        def sync_task_materials(self, state) -> None:
            self.states.append(state)

    database = SQLiteStore(":memory:")
    database.initialize()
    projection = MeetingProjection()
    runtime = MockRuntime(result_factory=_result)

    state = asyncio.run(
        engine.run_live_task_multi_agent(
            _task(),
            _agents(),
            store=database,
            run_store=RunStore(database),
            runtime=runtime,
            meeting_service=projection,
            candidate_writer=lambda _state, invocation, _result: {
                "candidate_id": f"candidate-{invocation.agent_id}",
            },
        )
    )

    assert state.status == "awaiting_review"
    assert projection.states == [state]
    database.close()


def test_task_bridge_runtime_factory_forwards_runtime_name_once(monkeypatch) -> None:
    database = SQLiteStore(":memory:")
    database.initialize()
    calls: list[dict] = []
    runtime = MockRuntime(result_factory=_result)

    def runtime_factory(**kwargs):
        calls.append(kwargs)
        return runtime

    monkeypatch.setattr(engine, "create_runtime", runtime_factory)

    state = asyncio.run(
        engine.run_live_task_multi_agent(
            _task(),
            _agents(),
            store=database,
            run_store=RunStore(database),
            candidate_writer=lambda _state, invocation, _result: {
                "candidate_id": f"candidate-{invocation.agent_id}",
            },
        )
    )

    assert state.status == "awaiting_review"
    assert len(calls) == 1
    assert calls[0]["runtime_name"] == "pi"
    database.close()


def test_task_bridge_retries_requested_agent_and_followers_only() -> None:
    database = SQLiteStore(":memory:")
    database.initialize()
    run_store = RunStore(database)
    calls: list[str] = []
    fail_once = {"agent-2"}

    def first_result(invocation: AgentInvocation) -> AgentResult:
        calls.append(invocation.agent_id)
        if invocation.agent_id in fail_once:
            fail_once.remove(invocation.agent_id)
            return AgentResult(
                agent_id=invocation.agent_id,
                status="error",
                content="",
                error="transient provider error",
                data_space=invocation.data_space,
            )
        return _result(invocation)

    state = asyncio.run(
        engine.run_live_task_multi_agent(
            _task(),
            _agents(),
            store=database,
            run_store=run_store,
            runtime=MockRuntime(result_factory=first_result),
            candidate_writer=lambda _state, invocation, _result: {
                "candidate_id": f"candidate-{invocation.agent_id}",
            },
        )
    )
    assert state.status == "failed"
    assert calls == ["agent-1", "agent-2"]

    retry_calls: list[str] = []

    def retry_result(invocation: AgentInvocation) -> AgentResult:
        retry_calls.append(invocation.agent_id)
        return _result(invocation)

    resumed = run_store.get(state.run_id)
    assert resumed is not None
    retried = asyncio.run(
        engine.run_live_task_multi_agent(
            _task(),
            _agents(),
            store=database,
            run_store=run_store,
            state=resumed,
            runtime=MockRuntime(result_factory=retry_result),
            retry_agent_id="agent-2",
            candidate_writer=lambda _state, invocation, _result: {
                "candidate_id": f"candidate-{invocation.agent_id}",
            },
        )
    )

    assert retried.status == "awaiting_review"
    assert retry_calls == ["agent-2", "agent-3"]
    invocations = [
        step.payload
        for step in retried.steps
        if step.kind == "invocation" and step.actor == "agent-2"
    ]
    assert invocations[-1]["attempt"] == 2
    assert invocations[-1]["retry_of"]
    database.close()
