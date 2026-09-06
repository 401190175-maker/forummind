"""RED tests for the ForumMind-owned multi-Agent coordinator."""

import asyncio
import json

import pytest

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.meeting.service import MeetingService
from app.orchestration.coordinator import MultiAgentRunCoordinator
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario
from app.storage.repositories import MeetingRepository
from app.storage.sqlite_store import SQLiteStore


MASTER_IDS = ["agent-ms-1", "agent-ms-2", "agent-ms-3"]


def _spec(agent_id: str, role: str, name: str | None = None) -> dict:
    return {
        "agent_id": agent_id,
        "name": name or agent_id,
        "role": role,
        "primary_ability": "科研分析",
        "allowed_tools": ["memory.query", "literature.search"],
        "specialty_domain": "泡沫混凝土" if role == "postdoc" else None,
        "profile": {
            "agent_id": agent_id,
            "name": name or agent_id,
            "role": role,
            "primary_ability": "科研分析",
            "allowed_tools": ["memory.query", "literature.search"],
            "allowed_data_spaces": ["synthetic"],
            "specialty_domain": "泡沫混凝土" if role == "postdoc" else None,
        },
    }


def _claim(invocation: AgentInvocation) -> AgentResult:
    content = f"{invocation.agent_id} 的独立判断"
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=content,
        structured_output={
            "statement": content,
            "boundary": "当前合成课题条件",
            "prediction": f"{invocation.agent_id} 的可观察预测",
            "falsification_condition": "控制孔结构后差异消失",
        },
        data_space=invocation.data_space,
    )


def _state(store: RunStore, *, with_postdoc: bool = True):
    return store.create(
        "gc-1",
        "live",
        runtime_name="mock",
        agent_specs=[_spec(agent_id, "master_student") for agent_id in MASTER_IDS],
        review_agent_spec=_spec("agent-phd-1", "phd_student"),
        postdoc_agent_spec=_spec("agent-postdoc-1", "postdoc") if with_postdoc else None,
        task_context={"topic_name": "泡沫混凝土", "task": "比较候选机制"},
    )


def test_coordinator_runs_role_pipeline_and_separates_pi_decision() -> None:
    def result(invocation: AgentInvocation) -> AgentResult:
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="博士审查完成",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ],
                    "disposition": "approved",
                },
                data_space=invocation.data_space,
            )
        if invocation.phase == "postdoc_exchange":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="泡沫混凝土专业综合",
                structured_output={
                    "summary": "综合三个候选观点",
                    "recommendations": ["补充孔结构观察"],
                    "limitations": ["仍需判别实验"],
                    "open_questions": ["因果边界是否稳定"],
                },
                data_space=invocation.data_space,
            )
        return _claim(invocation)

    store = RunStore()
    state = _state(store)
    runtime = MockRuntime(result_factory=result)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    outcome = asyncio.run(coordinator.run_cycle(state.run_id))

    assert [item.phase for item in runtime.invocations] == [
        "independent_analysis",
        "independent_analysis",
        "independent_analysis",
        "review_gate",
        "postdoc_exchange",
    ]
    assert [item.role for item in runtime.invocations] == [
        "master_student",
        "master_student",
        "master_student",
        "phd_student",
        "postdoc",
    ]
    assert outcome.state.status == "awaiting_decision"
    assert state.pi_suggestion["source"] == "live"
    assert state.pi_suggestion["source_refs"]
    assert any(step.kind == "suggested_decision" for step in state.steps)
    assert not any(step.kind == "decision" for step in state.steps)
    assert state.review_result["falsification_conditions"] == ["可推翻条件"]
    assert state.postdoc_result["summary"] == "综合三个候选观点"


def test_coordinator_normalizes_provider_review_category_arrays() -> None:
    def result(invocation: AgentInvocation) -> AgentResult:
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="博士审查完成",
                structured_output={
                    "counterexample": ["反例"],
                    "falsification_condition": ["可推翻条件"],
                    "missing_observation": ["缺失观察"],
                },
                data_space=invocation.data_space,
            )
        if invocation.phase == "postdoc_exchange":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="泡沫混凝土专业综合",
                structured_output={
                    "summary": "综合三个候选观点",
                    "recommendations": ["补充孔结构观察"],
                    "limitations": ["仍需判别实验"],
                    "open_questions": ["因果边界是否稳定"],
                },
                data_space=invocation.data_space,
            )
        return _claim(invocation)

    store = RunStore()
    state = _state(store)
    runtime = MockRuntime(result_factory=result)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))

    assert state.status == "awaiting_decision"
    assert state.review_result["counterexamples"] == ["反例"]


def test_injected_non_pi_runtime_is_not_labeled_as_pi_evidence() -> None:
    store = RunStore()
    state = store.create(
        "gc-1",
        "live",
        agent_specs=[_spec(agent_id, "master_student") for agent_id in MASTER_IDS],
        runtime_name="",
    )
    runtime = MockRuntime(result_factory=_claim)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))

    claims = [step for step in state.steps if step.kind == "claim"]
    assert claims
    assert all(step.payload["runtime"] == "mock" for step in claims)
    assert all("Runtime: `mock`" in artifact["content"] for artifact in state.artifacts)


def test_task_scoped_coordinator_preserves_real_scope_and_candidate_boundary() -> None:
    captured: dict[str, object] = {}

    def result(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content=f"{invocation.agent_id} 的真实候选",
            structured_output={
                "claim": f"{invocation.agent_id} 的资料判断",
                "evidence_refs": ["chunk-1"],
                "reasoning_summary": "只基于授权资料",
                "uncertainty": "仍需更多样本",
                "next_action": "补充对照实验",
            },
            data_space=invocation.data_space,
        )

    store = RunStore()
    state = store.create(
        "gc-real",
        "live",
        task_id="task-real",
        runtime_name="pi",
        agent_specs=[_spec(agent_id, "master_student") for agent_id in MASTER_IDS],
        task_context={
            "task_id": "task-real",
            "data_space": "desensitized_real",
            "document_ids": ["doc-1"],
            "allowed_document_ids": ["doc-1"],
            "output_contract": "research_claim",
            "completion_mode": "candidate_review",
        },
    )
    runtime = MockRuntime(result_factory=result)
    registry = object()

    def runtime_factory(**kwargs):
        captured.update(kwargs)
        return runtime

    coordinator = MultiAgentRunCoordinator(
        store,
        load_scenario("foam_concrete_case"),
        runtime_factory=runtime_factory,
        tool_registry=registry,
        context_factory=lambda invocation: captured.setdefault("context", invocation),
    )

    asyncio.run(coordinator.run_cycle(state.run_id))

    assert captured["tool_registry"] is registry
    assert [invocation.task_id for invocation in runtime.invocations] == ["task-real"] * 3
    assert [invocation.document_scope for invocation in runtime.invocations] == [["doc-1"]] * 3
    assert state.status == "awaiting_review"
    assert state.phase == "awaiting_review"
    assert [step.kind for step in state.steps] == ["invocation", "candidate"] * 3
    assert state.memory.entries() == []


def test_task_scoped_invocation_does_not_duplicate_persisted_candidate_results() -> None:
    captured: list[AgentInvocation] = []

    def result(invocation: AgentInvocation) -> AgentResult:
        captured.append(invocation)
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="候选" * 15_000,
            structured_output={
                "claim": f"{invocation.agent_id} 的资料判断",
                "evidence_refs": ["chunk-1"],
                "reasoning_summary": "只基于授权资料",
                "uncertainty": "仍需更多样本",
                "next_action": "补充对照实验",
            },
            data_space=invocation.data_space,
        )

    store = RunStore()
    state = store.create(
        "gc-real",
        "live",
        task_id="task-real",
        runtime_name="pi",
        agent_specs=[_spec(agent_id, "master_student") for agent_id in MASTER_IDS],
        task_context={
            "task_id": "task-real",
            "data_space": "desensitized_real",
            "output_contract": "research_claim",
            "completion_mode": "candidate_review",
        },
    )
    runtime = MockRuntime(result_factory=result)
    coordinator = MultiAgentRunCoordinator(
        store,
        load_scenario("foam_concrete_case"),
        runtime_factory=lambda **_: runtime,
    )

    asyncio.run(coordinator.run_cycle(state.run_id))

    third = captured[2]
    task_context = third.context["task_context"]
    assert isinstance(task_context, dict)
    assert "candidate_results" not in task_context
    payload = third.model_dump(mode="json")
    sizes = {
        key: len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        for key, value in payload.items()
    }
    assert sum(sizes.values()) < 256 * 1024, sizes


def test_reviewer_rejection_blocks_postdoc_and_meeting() -> None:
    def result(invocation: AgentInvocation) -> AgentResult:
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="审查拒回",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ],
                    "disposition": "rejected",
                },
                data_space=invocation.data_space,
            )
        return _claim(invocation)

    store = RunStore()
    state = _state(store)
    runtime = MockRuntime(result_factory=result)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))

    assert state.status == "failed"
    assert state.phase == "failed"
    assert "审查门" in state.error
    review_invocations = [
        step for step in state.steps
        if step.kind == "invocation" and step.actor == "agent-phd-1"
    ]
    assert len(review_invocations) == 1
    assert review_invocations[0].payload["status"] == "rejected"
    assert not any(item.phase == "postdoc_exchange" for item in runtime.invocations)
    assert not any(step.phase == "meeting" for step in state.steps)


def test_invalid_review_disposition_keeps_invocation_identity_for_retry() -> None:
    def invalid_review(invocation: AgentInvocation) -> AgentResult:
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="博士审查",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ],
                    "disposition": "invalid",
                },
                data_space=invocation.data_space,
            )
        return _claim(invocation)

    store = RunStore()
    state = _state(store, with_postdoc=False)
    runtime = MockRuntime(result_factory=invalid_review)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))

    failure = next(
        step
        for step in reversed(state.steps)
        if step.actor == "agent-phd-1" and step.kind == "invocation"
    )
    assert failure.payload["invocation_id"] == runtime.invocations[-1].invocation_id
    assert failure.payload["attempt"] == 1


def test_failed_invocation_is_projected_to_meeting_service_immediately() -> None:
    database = SQLiteStore(":memory:")
    database.initialize()
    store = RunStore(database)
    state = _state(store, with_postdoc=False)
    runtime = MockRuntime(
        result_factory=lambda invocation: AgentResult(
            agent_id=invocation.agent_id,
            status="error",
            content="",
            error="provider unavailable",
            data_space=invocation.data_space,
        )
    )
    meeting = MeetingService(store, MeetingRepository(database))
    coordinator = MultiAgentRunCoordinator(
        store,
        load_scenario("foam_concrete_case"),
        runtime_factory=lambda **_: runtime,
        meeting_service=meeting,
    )

    try:
        asyncio.run(coordinator.run_cycle(state.run_id))
        events = MeetingRepository(database).list_events(state.run_id)

        assert [event["kind"] for event in events] == ["failure"]
    finally:
        database.close()


def test_retry_runs_only_failed_agent_and_unfinished_followers() -> None:
    failures = {"agent-ms-2"}
    calls: list[str] = []

    def result(invocation: AgentInvocation) -> AgentResult:
        calls.append(invocation.agent_id)
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="博士审查",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ],
                    "disposition": "approved",
                },
                data_space=invocation.data_space,
            )
        if invocation.agent_id in failures:
            failures.remove(invocation.agent_id)
            return AgentResult(
                agent_id=invocation.agent_id,
                status="error",
                content="",
                error="temporary provider failure",
                data_space=invocation.data_space,
            )
        return _claim(invocation)

    store = RunStore()
    state = _state(store, with_postdoc=False)
    runtime = MockRuntime(result_factory=result)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))
    assert calls == ["agent-ms-1", "agent-ms-2"]
    first_failed_invocation = runtime.invocations[-1].invocation_id

    asyncio.run(coordinator.retry_agent(state.run_id, "agent-ms-2"))

    assert calls == ["agent-ms-1", "agent-ms-2", "agent-ms-2", "agent-ms-3", "agent-phd-1"]
    assert runtime.invocations[1].invocation_id != runtime.invocations[2].invocation_id
    assert runtime.invocations[2].attempt == 2
    assert runtime.invocations[2].retry_of == first_failed_invocation
    assert state.status == "awaiting_decision"
    assert len([step for step in state.steps if step.actor == "agent-ms-1" and step.kind == "claim"]) == 1
    assert not any(step.kind == "claim" and step.payload.get("source") == "scenario" for step in state.steps)


def test_retrying_review_does_not_reinvoke_completed_masters() -> None:
    calls: list[tuple[str, str]] = []
    review_failures = 1

    def result(invocation: AgentInvocation) -> AgentResult:
        nonlocal review_failures
        calls.append((invocation.phase, invocation.agent_id))
        if invocation.phase == "review_gate":
            if review_failures:
                review_failures -= 1
                return AgentResult(
                    agent_id=invocation.agent_id,
                    status="error",
                    content="",
                    error="temporary review failure",
                    data_space=invocation.data_space,
                )
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="博士审查",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ],
                    "disposition": "approved",
                },
                data_space=invocation.data_space,
            )
        return _claim(invocation)

    store = RunStore()
    state = _state(store, with_postdoc=False)
    runtime = MockRuntime(result_factory=result)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))
    asyncio.run(coordinator.retry_agent(state.run_id, "agent-phd-1"))

    assert calls == [
        ("independent_analysis", "agent-ms-1"),
        ("independent_analysis", "agent-ms-2"),
        ("independent_analysis", "agent-ms-3"),
        ("review_gate", "agent-phd-1"),
        ("review_gate", "agent-phd-1"),
    ]
    assert state.status == "awaiting_decision"


def test_retrying_postdoc_does_not_reinvoke_completed_upstream_agents() -> None:
    calls: list[tuple[str, str]] = []
    postdoc_failures = 1

    def result(invocation: AgentInvocation) -> AgentResult:
        nonlocal postdoc_failures
        calls.append((invocation.phase, invocation.agent_id))
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="博士审查",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ],
                    "disposition": "approved",
                },
                data_space=invocation.data_space,
            )
        if invocation.phase == "postdoc_exchange":
            if postdoc_failures:
                postdoc_failures -= 1
                return AgentResult(
                    agent_id=invocation.agent_id,
                    status="error",
                    content="",
                    error="temporary postdoc failure",
                    data_space=invocation.data_space,
                )
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="泡沫混凝土专业综合",
                structured_output={
                    "summary": "综合候选观点",
                    "recommendations": ["补充观察"],
                    "limitations": ["仍需实验"],
                    "open_questions": ["边界是否稳定"],
                },
                data_space=invocation.data_space,
            )
        return _claim(invocation)

    store = RunStore()
    state = _state(store)
    runtime = MockRuntime(result_factory=result)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))
    asyncio.run(coordinator.retry_agent(state.run_id, "agent-postdoc-1"))

    assert calls == [
        ("independent_analysis", "agent-ms-1"),
        ("independent_analysis", "agent-ms-2"),
        ("independent_analysis", "agent-ms-3"),
        ("review_gate", "agent-phd-1"),
        ("postdoc_exchange", "agent-postdoc-1"),
        ("postdoc_exchange", "agent-postdoc-1"),
    ]
    assert state.status == "awaiting_decision"


def test_retry_attempt_gets_a_distinct_session_scope() -> None:
    invocation_one = AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student",
        task="task", attempt=1,
    )
    invocation_two = invocation_one.model_copy(
        update={"invocation_id": "inv-retry", "attempt": 2, "retry_of": invocation_one.invocation_id}
    )
    assert invocation_two.invocation_id != invocation_one.invocation_id
    assert invocation_two.retry_of == invocation_one.invocation_id


def test_retry_agent_stops_at_the_per_agent_attempt_cap() -> None:
    def always_fails(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="error",
            content="",
            error="provider unavailable",
            data_space=invocation.data_space,
        )

    store = RunStore()
    state = _state(store, with_postdoc=False)
    runtime = MockRuntime(result_factory=always_fails)
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime
    )

    asyncio.run(coordinator.run_cycle(state.run_id))
    asyncio.run(coordinator.retry_agent(state.run_id, "agent-ms-1"))

    with pytest.raises(ValueError, match="最大重试次数"):
        asyncio.run(coordinator.retry_agent(state.run_id, "agent-ms-1"))


def test_postdoc_formal_projection_requires_request_and_keeps_suggestion_separate() -> None:
    database = SQLiteStore(":memory:")
    database.initialize()
    store = RunStore(database)
    state = _state(store)
    runtime = MockRuntime(result_factory=lambda invocation: (
        AgentResult(
            agent_id=invocation.agent_id, status="ok", content="泡沫混凝土专业综合",
            structured_output={
                "summary": "综合候选观点", "recommendations": ["补充观察"],
                "limitations": ["仍需实验"], "open_questions": ["边界是否稳定"],
            }, data_space=invocation.data_space,
        ) if invocation.phase == "postdoc_exchange" else (
            AgentResult(
                agent_id=invocation.agent_id, status="ok", content="博士审查",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ], "disposition": "approved",
                }, data_space=invocation.data_space,
            ) if invocation.phase == "review_gate" else _claim(invocation)
        )
    ))
    meeting = MeetingService(store, MeetingRepository(database))
    coordinator = MultiAgentRunCoordinator(
        store, load_scenario("foam_concrete_case"), runtime_factory=lambda **_: runtime,
        meeting_service=meeting,
    )

    asyncio.run(coordinator.run_cycle(state.run_id))

    events = meeting.list_meeting_events(state.run_id)
    assert [event.kind for event in events] == [
        "master_report", "master_report", "master_report",
        "postdoc_request", "postdoc_response", "suggested_decision",
    ]
    assert not any(step.kind == "decision" for step in state.steps)
