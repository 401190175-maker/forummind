"""Persistent evidence for the runtime-driven master/review/meeting journey."""

import asyncio

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.meeting.service import MeetingService
from app.orchestration import engine
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario
from app.storage.repositories import ArtifactRepository, MeetingRepository
from app.storage.sqlite_store import SQLiteStore


MASTER_IDS = ["agent-ms-1", "agent-ms-2", "agent-ms-3"]


def _result(invocation: AgentInvocation) -> AgentResult:
    if invocation.phase == "review_gate":
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="博士会前质量审查",
            structured_output={
                "items": [
                    {"kind": "counterexample", "content": "反例"},
                    {"kind": "falsification_condition", "content": "可推翻条件"},
                    {"kind": "missing_observation", "content": "缺失观察"},
                ]
            },
            data_space=invocation.data_space,
        )
    content = f"{invocation.agent_id} 的独立 Markdown 判断"
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=content,
        structured_output={
            "statement": content,
            "boundary": "当前合成课题条件",
            "prediction": f"{invocation.agent_id} 的可观察预测",
            "falsification_condition": f"{invocation.agent_id} 的可推翻条件",
        },
        data_space=invocation.data_space,
    )


def _spec(agent_id: str, role: str, name: str) -> dict:
    return {
        "agent_id": agent_id,
        "name": name,
        "role": role,
        "primary_ability": "独立科研分析",
        "profile": {
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "primary_ability": "独立科研分析",
        },
    }


def test_live_run_persists_independent_master_markdown_and_phd_review_gate(
    tmp_path, monkeypatch
) -> None:
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    meeting = MeetingService(store, MeetingRepository(database))
    runtime = MockRuntime(result_factory=_result)
    monkeypatch.setattr(engine, "create_runtime", lambda **_: runtime)
    state = store.create(
        "group-runtime-journey",
        "live",
        runtime_name="mock",
        agent_specs=[_spec(agent_id, "master_student", agent_id) for agent_id in MASTER_IDS],
        review_agent_spec=_spec("agent-phd-1", "phd_student", "博士"),
        task_context={
            "topic_name": "泡沫混凝土课题",
            "topic_summary": "验证独立观点产物和会前审查",
            "initial_intent": "比较候选机制",
        },
    )

    try:
        asyncio.run(
            engine.run_live(
                load_scenario("foam_concrete_case"),
                state,
                meeting_service=meeting,
            )
        )

        artifacts = ArtifactRepository(database).list_for_run(state.run_id)
        events = meeting.list_meeting_events(state.run_id)
        review_steps = [step for step in state.steps if step.phase == "review_gate"]
        phd_steps = [step for step in state.steps if step.actor == "agent-phd-1"]

        assert state.status == "awaiting_decision"
        assert len(artifacts) == len(MASTER_IDS)
        assert {artifact["agent_id"] for artifact in artifacts} == set(MASTER_IDS)
        assert all(artifact["filename"].endswith(".md") for artifact in artifacts)
        assert all(artifact["content"].startswith("# ") for artifact in artifacts)
        assert len(review_steps) == 3
        assert phd_steps == review_steps
        assert [event.kind for event in events] == ["master_report"] * 3
        assert all(event.actor_role == "master_student" for event in events)
        assert all(
            any(ref == artifact["artifact_id"] for ref in event.source_refs)
            for event in events
            for artifact in artifacts
            if artifact["agent_id"] == event.actor_id
        )
        assert all(event.actor_role != "phd_student" for event in events)

        meeting.apply_pi_decision(state.run_id, "approved", "保留最小判别实验")
        final_events = meeting.list_meeting_events(state.run_id)
        assert final_events[-1].kind == "decision"
        assert final_events[-1].actor_role == "pi"
        assert sum(event.kind == "decision" for event in final_events) == 1
    finally:
        database.close()
