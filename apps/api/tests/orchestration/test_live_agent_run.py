"""Frozen multi-Agent live Run behavior."""

import asyncio

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.orchestration import engine
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario


def _specs() -> list[dict]:
    return [
        {
            "agent_id": "agent-live-1",
            "role": "master_student",
            "primary_ability": "机制",
        },
        {
            "agent_id": "agent-live-2",
            "role": "master_student",
            "primary_ability": "实验",
        },
        {
            "agent_id": "agent-live-3",
            "role": "master_student",
            "primary_ability": "证据",
        },
    ]


def _valid(invocation: AgentInvocation) -> AgentResult:
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=f"{invocation.agent_id} 的独立候选",
        structured_output={
            "statement": f"{invocation.agent_id} 的判断",
            "boundary": "合成材料边界",
            "prediction": f"{invocation.agent_id} 的可观察预测",
            "falsification_condition": "控制孔结构后差异消失",
        },
        data_space=invocation.data_space,
    )


def _new_live() -> object:
    return RunStore().create(
        "gc-1", "live", agent_specs=_specs(), runtime_name="pi"
    )


def test_live_run_invokes_three_frozen_agents_in_order(monkeypatch):
    runtime = MockRuntime(result_factory=_valid)
    monkeypatch.setattr(engine, "create_runtime", lambda *args, **kwargs: runtime)
    state = _new_live()

    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    assert [item.agent_id for item in runtime.invocations] == [
        "agent-live-1",
        "agent-live-2",
        "agent-live-3",
    ]
    outcomes = [step for step in state.steps if step.kind == "invocation"]
    assert [step.actor for step in outcomes] == [
        "agent-live-1",
        "agent-live-2",
        "agent-live-3",
    ]
    assert all(step.payload["status"] == "ok" for step in outcomes)
    assert all(step.payload["runtime"] == "mock" for step in outcomes)
    assert all("source_refs" in step.payload for step in outcomes)
    assert state.status == "awaiting_decision"

    frozen = state.memory.latest("Claim", object_key="agent-live-1")
    assert frozen is not None
    assert frozen.payload["boundary"] == "合成材料边界"
    assert frozen.payload["prediction"] == "agent-live-1 的可观察预测"
    assert frozen.payload["falsification_condition"] == "控制孔结构后差异消失"
    assert frozen.payload["status"] == "frozen"

    claims = [step for step in state.steps if step.kind == "claim"]
    assert [step.actor for step in claims] == [
        "agent-live-1",
        "agent-live-2",
        "agent-live-3",
    ]
    assert all(step.payload["source"] == "live" for step in claims)


def test_live_failure_preserves_prior_claim_and_stops_following_agents(monkeypatch):
    def result(invocation: AgentInvocation) -> AgentResult:
        if invocation.agent_id == "agent-live-2":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="error",
                content="",
                error="Pi agent failed",
            )
        return _valid(invocation)

    runtime = MockRuntime(result_factory=result)
    monkeypatch.setattr(engine, "create_runtime", lambda *args, **kwargs: runtime)
    state = _new_live()

    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    assert [item.agent_id for item in runtime.invocations] == [
        "agent-live-1",
        "agent-live-2",
    ]
    assert state.status == "failed"
    assert state.phase == "failed"
    assert "Pi agent failed" in state.error
    assert any(
        step.kind == "claim"
        and step.actor == "agent-live-1"
        and step.payload.get("source") == "live"
        for step in state.steps
    )
    assert not any(step.actor == "agent-live-3" for step in state.steps)
    assert not any(
        step.kind == "claim" and step.payload.get("source") == "scenario"
        for step in state.steps
    )
    failed = [
        step
        for step in state.steps
        if step.kind == "invocation" and step.actor == "agent-live-2"
    ]
    assert len(failed) == 1
    assert failed[0].payload.items() >= {
        "runtime": "mock",
        "agent_id": "agent-live-2",
        "status": "error",
        "error": "Pi agent failed",
        "source_refs": [],
    }.items()
    assert failed[0].payload["invocation_id"]
    assert failed[0].payload["attempt"] == 1
    assert failed[0].payload["retry_of"] == ""


def test_live_rejects_invalid_candidate_without_writing_claim(monkeypatch):
    def invalid_result(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="候选",
            structured_output={"statement": "判断"},
            data_space=invocation.data_space,
        )

    runtime = MockRuntime(result_factory=invalid_result)
    monkeypatch.setattr(engine, "create_runtime", lambda *args, **kwargs: runtime)
    state = _new_live()

    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    assert state.status == "failed"
    assert state.phase == "failed"
    assert state.error.endswith("must be non-empty text")
    assert [step for step in state.steps if step.kind == "claim"] == []
    assert len(runtime.invocations) == 1
    failure = next(step for step in state.steps if step.kind == "invocation")
    assert failure.payload["status"] == "error"


def test_live_requires_frozen_agent_specs(monkeypatch):
    runtime = MockRuntime(result_factory=_valid)
    monkeypatch.setattr(engine, "create_runtime", lambda *args, **kwargs: runtime)
    state = RunStore().create("gc-1", "live", runtime_name="pi")

    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    assert runtime.invocations == []
    assert state.status == "failed"
    assert "三个" in state.error
    assert [step for step in state.steps if step.kind == "claim"] == []


def test_runtime_event_projection_failure_keeps_the_injected_runtime_label(monkeypatch):
    class RuntimeWithInvalidEvents(MockRuntime):
        runtime_name = "mock"

        @property
        def last_events(self):
            invocation = self.invocations[-1]
            return {
                invocation.invocation_id: [{
                    "event_id": "event-invalid",
                    "cursor": 1,
                    "session_id": "session-1",
                    "invocation_id": invocation.invocation_id,
                    "run_id": "foreign-run",
                    "group_chat_id": invocation.group_chat_id,
                    "agent_id": invocation.agent_id,
                    "phase": invocation.phase,
                    "type": "text_delta",
                    "payload": {"content_delta": "candidate"},
                    "data_space": invocation.data_space,
                    "timestamp": 1.0,
                }]
            }

    runtime = RuntimeWithInvalidEvents(result_factory=_valid)
    monkeypatch.setattr(engine, "create_runtime", lambda *args, **kwargs: runtime)
    state = _new_live()

    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    failure = next(step for step in state.steps if step.kind == "invocation")
    assert failure.payload["runtime"] == "mock"
