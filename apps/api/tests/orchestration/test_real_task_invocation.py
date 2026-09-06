import asyncio
from types import SimpleNamespace

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.schemas import AgentResult
from app.documents.chunker import DocumentChunk
from app.documents.repository import DocumentRepository
from app.documents.schemas import DocumentIndexJob, DocumentRecord
from app.domain.schemas import AgentProfile
from app.orchestration.coordinator import MultiAgentRunCoordinator
from app.orchestration import engine
from app.orchestration.run_store import RunState, RunStep, RunStore
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def test_run_live_task_uses_task_scope_and_stops_at_review(monkeypatch, tmp_path):
    database = SQLiteStore(tmp_path / "real-task.db")
    database.initialize()
    documents = DocumentRepository(database)
    documents.save(DocumentRecord(
        document_id="doc-a", group_chat_id="gc-1", filename="source.txt",
        mime_type="text/plain", size_bytes=10, sha256="a" * 64,
        storage_key="documents/a.txt", data_space="desensitized_real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    documents.replace_chunks("doc-a", [DocumentChunk(
        document_id="doc-a", chunk_id="chunk-a", chunk_index=0,
        content="强度结果", page_or_location="page 1", char_start=0, char_end=4,
    )])
    documents.save_index_job(DocumentIndexJob(
        document_id="doc-a", status="ready", retry_count=0,
        started_at=1.0, finished_at=2.0, updated_at=2.0,
    ))
    task = ResearchTask(
        task_id="task-1", group_chat_id="gc-1", title="研究任务",
        question="资料中的强度趋势是什么？", document_ids=["doc-a"],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    ResearchTaskRepository(database).create(task)
    agent = AgentProfile(
        agent_id="agent-1", name="分析 Agent", role="master_student",
        primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
        allowed_tools=["knowledge.search"],
    )
    runtime = MockRuntime(result_factory=lambda invocation: AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content="资料支持该候选主张。",
        structured_output={
            "claim": "孔结构增大时抗压强度下降。",
            "evidence_refs": ["chunk-a"],
            "reasoning_summary": "来自上传资料。",
            "uncertainty": "尚需更多样本。",
            "next_action": "补充对照实验。",
        },
        data_space=invocation.data_space,
    ))
    monkeypatch.setattr(engine, "create_runtime", lambda *args, **kwargs: runtime)

    state = asyncio.run(engine.run_live_task(task, agent, store=database))

    assert state.task_id == "task-1"
    assert state.status == "awaiting_review"
    assert runtime.invocations[0].data_space == "desensitized_real"
    assert runtime.invocations[0].document_scope == ["doc-a"]
    assert state.steps[0].payload["runtime"] == "mock"
    assert state.memory.entries() == []
    database.close()


def test_run_live_task_binds_native_session_to_invocation_identity():
    class NativeSessionRuntime(MockRuntime):
        def __init__(self):
            super().__init__(result_factory=lambda invocation: AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="候选结果",
                structured_output={
                    "claim": "资料支持该趋势",
                    "evidence_refs": ["chunk-a"],
                    "reasoning_summary": "来自授权资料",
                    "uncertainty": "样本有限",
                    "next_action": "补充对照实验",
                },
                data_space=invocation.data_space,
            ))
            self.last_sessions = {}

        async def invoke(self, invocation):
            result = await super().invoke(invocation)
            self.last_sessions[invocation.agent_id] = SimpleNamespace(
                session_id="native-session-1",
                session_scope="gc-1/run-1/agent-1",
                cursor=1,
            )
            return result

    task = ResearchTask(
        task_id="task-session-ref", group_chat_id="gc-1", title="研究任务",
        question="资料中的强度趋势是什么？", document_ids=[],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    agent = AgentProfile(
        agent_id="agent-1", name="分析 Agent", role="master_student",
        primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
    )
    runtime = NativeSessionRuntime()

    state = asyncio.run(engine.run_live_task(task, agent, runtime=runtime))

    assert state.session_refs["agent-1"].invocation_id == runtime.invocations[0].invocation_id


def test_run_live_task_multi_agent_runs_frozen_agents_and_persists_candidates(monkeypatch, tmp_path):
    database = SQLiteStore(tmp_path / "real-task-multi-agent.db")
    database.initialize()
    documents = DocumentRepository(database)
    documents.save(DocumentRecord(
        document_id="doc-a", group_chat_id="gc-1", filename="source.txt",
        mime_type="text/plain", size_bytes=10, sha256="a" * 64,
        storage_key="documents/a.txt", data_space="desensitized_real", status="ready",
        created_at=1.0, updated_at=1.0,
    ))
    documents.replace_chunks("doc-a", [DocumentChunk(
        document_id="doc-a", chunk_id="chunk-a", chunk_index=0,
        content="强度结果", page_or_location="page 1", char_start=0, char_end=4,
    )])
    documents.save_index_job(DocumentIndexJob(
        document_id="doc-a", status="ready", retry_count=0,
        started_at=1.0, finished_at=2.0, updated_at=2.0,
    ))
    task = ResearchTask(
        task_id="task-multi", group_chat_id="gc-1", title="研究任务",
        question="资料中的强度趋势是什么？", document_ids=["doc-a"],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    ResearchTaskRepository(database).create(task)
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
            allowed_tools=["knowledge.search"],
        )
        for index in range(1, 4)
    ]
    runtime = MockRuntime(result_factory=lambda invocation: AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=f"{invocation.agent_id} 资料候选",
        structured_output={
            "claim": "孔结构增大时抗压强度下降。",
            "evidence_refs": ["chunk-a"],
            "reasoning_summary": "来自上传资料。",
            "uncertainty": "尚需更多样本。",
            "next_action": "补充对照实验。",
        },
        data_space=invocation.data_space,
    ))
    monkeypatch.setattr(engine, "create_runtime", lambda *args, **kwargs: runtime)

    state = asyncio.run(engine.run_live_task_multi_agent(
        task,
        agents,
        store=database,
    ))

    assert [invocation.agent_id for invocation in runtime.invocations] == [
        "agent-1", "agent-2", "agent-3",
    ]
    assert all(invocation.task_id == "task-multi" for invocation in runtime.invocations)
    assert all(invocation.document_scope == ["doc-a"] for invocation in runtime.invocations)
    assert state.status == "awaiting_review"
    assert len(state.candidate_ids) == 3
    assert state.memory.entries() == []
    database.close()


def test_real_task_candidate_prompt_declares_the_research_claim_contract():
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-contract-prompt", group_chat_id="gc-1", title="研究任务",
        question="资料中的强度趋势是什么？", document_ids=[],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
        )
        for index in range(1, 4)
    ]
    runtime = MockRuntime(result_factory=lambda invocation: AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content="资料支持该候选主张。",
        structured_output={
            "claim": "孔结构增大时抗压强度下降。",
            "evidence_refs": ["chunk-a"],
            "reasoning_summary": "来自上传资料。",
            "uncertainty": "尚需更多样本。",
            "next_action": "补充对照实验。",
        },
        data_space=invocation.data_space,
    ))

    asyncio.run(engine.run_live_task_multi_agent(task, agents, store=database, runtime=runtime))

    assert "claim、evidence_refs、reasoning_summary、uncertainty、next_action" in runtime.invocations[0].task
    database.close()


def test_real_multi_agent_preflight_rejects_synthetic_task_before_runtime():
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-synthetic", group_chat_id="gc-1", title="研究任务",
        question="合成任务不应进入真实多 Agent 流程", document_ids=[],
        data_space="synthetic", status="ready", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["synthetic"],
        )
        for index in range(1, 4)
    ]
    runtime = MockRuntime()

    state = asyncio.run(engine.run_live_task_multi_agent(
        task, agents, store=database, runtime=runtime,
    ))

    assert runtime.invocations == []
    assert state.status == "failed"
    assert "real data space" in state.error
    database.close()


def test_real_multi_agent_preflight_rejects_terminal_task_before_runtime():
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-completed", group_chat_id="gc-1", title="研究任务",
        question="已完成任务不应再次运行", document_ids=[],
        data_space="desensitized_real", status="completed", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
        )
        for index in range(1, 4)
    ]
    runtime = MockRuntime()

    state = asyncio.run(engine.run_live_task_multi_agent(
        task, agents, store=database, runtime=runtime,
    ))

    assert runtime.invocations == []
    assert state.status == "failed"
    assert "not runnable" in state.error
    database.close()


def test_real_multi_agent_retry_accepts_stale_failed_task_snapshot():
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-retry-stale-task", group_chat_id="gc-1", title="研究任务",
        question="恢复失败 Agent", document_ids=[],
        data_space="desensitized_real", status="failed", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
        )
        for index in range(1, 4)
    ]
    run_store = RunStore(database)
    state = run_store.create(
        "gc-1",
        "live",
        task_id=task.task_id,
        agent_specs=[agent.model_dump(mode="json") for agent in agents],
        task_context={
            "task_id": task.task_id,
            "data_space": task.data_space,
            "document_ids": [],
            "allowed_document_ids": [],
            "completion_mode": "candidate_review",
        },
    )
    state.status = "failed"
    state.phase = "failed"
    state.agent_attempts["agent-2"] = 1
    state.steps.append(RunStep(
        id="candidate-agent-1", phase="independent_analysis", kind="candidate",
        actor="agent-1", content="已完成候选",
        payload={"source": "live"}, timestamp=1.0,
    ))
    state.steps.append(RunStep(
        id="failed-agent-2", phase="independent_analysis", kind="invocation",
        actor="agent-2", content="暂时失败",
        payload={"status": "error", "attempt": 1, "invocation_id": "inv-agent-2-1"},
        timestamp=2.0,
    ))
    state.persist()

    def result(invocation):
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content=f"{invocation.agent_id} 候选",
            structured_output={
                "claim": "资料支持该候选主张",
                "evidence_refs": ["chunk-a"],
                "reasoning_summary": "只基于授权资料",
                "uncertainty": "样本有限",
                "next_action": "补充对照实验",
            },
            data_space=invocation.data_space,
        )

    runtime = MockRuntime(result_factory=result)
    resumed = asyncio.run(engine.run_live_task_multi_agent(
        task,
        agents,
        store=database,
        run_store=run_store,
        state=state,
        runtime=runtime,
        retry_agent_id="agent-2",
        candidate_writer=lambda _state, invocation, _result: {
            "candidate_id": f"candidate-{invocation.agent_id}",
        },
    ))

    assert [invocation.agent_id for invocation in runtime.invocations] == ["agent-2", "agent-3"], resumed.error
    assert resumed.status == "awaiting_review"
    assert state.error == ""
    database.close()


def test_real_multi_agent_role_pipeline_keeps_review_and_synthesis_as_candidates():
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-role-pipeline", group_chat_id="gc-1", title="研究任务",
        question="资料中的强度趋势是什么？", document_ids=["doc-a"],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
            allowed_tools=["knowledge.search"],
        )
        for index in range(1, 4)
    ]
    review_agent = AgentProfile(
        agent_id="agent-phd", name="博士审查", role="phd_student",
        primary_ability="质量审查", allowed_data_spaces=["desensitized_real"],
    )
    postdoc_agent = AgentProfile(
        agent_id="agent-postdoc", name="博士后综合", role="postdoc",
        primary_ability="专业综合", specialty_domain="泡沫混凝土",
        allowed_data_spaces=["desensitized_real"],
    )

    def result(invocation):
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id, status="ok", content="博士审查完成",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ],
                    "disposition": "approved",
                }, data_space=invocation.data_space,
            )
        if invocation.phase == "postdoc_exchange":
            return AgentResult(
                agent_id=invocation.agent_id, status="ok", content="泡沫混凝土专业综合",
                structured_output={
                    "summary": "综合候选观点",
                    "recommendations": ["补充观察"],
                    "limitations": ["仍需实验"],
                    "open_questions": ["边界是否稳定"],
                }, data_space=invocation.data_space,
            )
        return AgentResult(
            agent_id=invocation.agent_id, status="ok", content=f"{invocation.agent_id} 候选",
            structured_output={
                "claim": f"{invocation.agent_id} 的资料判断",
                "evidence_refs": ["chunk-a"],
                "reasoning_summary": "只基于授权资料",
                "uncertainty": "仍需更多样本",
                "next_action": "补充对照实验",
            }, data_space=invocation.data_space,
        )

    runtime = MockRuntime(result_factory=result)
    state = asyncio.run(engine.run_live_task_multi_agent(
        task,
        agents,
        store=database,
        runtime=runtime,
        review_agent=review_agent,
        postdoc_agent=postdoc_agent,
        candidate_writer=lambda _state, invocation, _result: {
            "candidate_id": f"candidate-{invocation.agent_id}",
        },
    ))

    assert [invocation.phase for invocation in runtime.invocations] == [
        "independent_analysis", "independent_analysis", "independent_analysis",
        "review_gate", "postdoc_exchange",
    ]
    assert {step.actor for step in state.steps if step.kind == "invocation"} == {
        "agent-1", "agent-2", "agent-3", "agent-phd", "agent-postdoc",
    }
    assert state.status == "awaiting_review"
    assert state.review_result["disposition"] == "approved"
    assert state.review_result["reviewed_candidate_ids"] == ["agent-1", "agent-2", "agent-3"]
    assert state.postdoc_result["summary"] == "综合候选观点"
    assert state.pi_suggestion["generated_by"] == "agent-postdoc"
    assert any(step.kind == "suggested_decision" for step in state.steps)
    candidate_step_ids = [step.id for step in state.steps if step.kind == "candidate"]
    review_invocation = next(item for item in runtime.invocations if item.phase == "review_gate")
    postdoc_invocation = next(item for item in runtime.invocations if item.phase == "postdoc_exchange")
    assert set(candidate_step_ids).issubset(review_invocation.input_refs)
    assert set(candidate_step_ids).issubset(postdoc_invocation.input_refs)
    assert state.memory.entries() == []

    recovered = __import__("app.orchestration.run_store", fromlist=["RunStore"]).RunStore(database).get(state.run_id)
    assert recovered is not None
    resumed_runtime = MockRuntime(result_factory=result)
    asyncio.run(engine.run_live_task_multi_agent(
        task,
        agents,
        store=database,
        runtime=resumed_runtime,
        state=recovered,
        review_agent=review_agent,
        postdoc_agent=postdoc_agent,
        candidate_writer=lambda _state, invocation, _result: {
            "candidate_id": f"candidate-{invocation.agent_id}",
        },
    ))
    assert resumed_runtime.invocations == []
    database.close()


def test_real_multi_agent_resume_rejects_changed_task_scope_without_overwriting_snapshot():
    database = SQLiteStore(":memory:")
    database.initialize()
    run_store = RunStore(database)
    original_scope = {
        "task_id": "task-original",
        "data_space": "desensitized_real",
        "document_ids": ["doc-original"],
        "allowed_document_ids": ["doc-original"],
    }
    state = run_store.create(
        "gc-1",
        "live",
        task_id="task-original",
        runtime_name="pi",
        agent_specs=[
            AgentProfile(
                agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
                primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
            ).model_dump(mode="json")
            for index in range(1, 4)
        ],
        task_context=original_scope,
    )
    changed_task = ResearchTask(
        task_id="task-changed", group_chat_id="gc-1", title="研究任务",
        question="资料中的强度趋势是什么？", document_ids=["doc-changed"],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
        )
        for index in range(1, 4)
    ]
    runtime = MockRuntime(result_factory=lambda invocation: AgentResult(
        agent_id=invocation.agent_id, status="error", content="",
        error="must not run", data_space=invocation.data_space,
    ))

    asyncio.run(engine.run_live_task_multi_agent(
        changed_task,
        agents,
        store=database,
        run_store=run_store,
        state=state,
        runtime=runtime,
    ))

    assert runtime.invocations == []
    assert state.status == "failed"
    assert "frozen" in state.error
    assert state.task_context == original_scope
    database.close()


def test_real_multi_agent_resume_rejects_empty_to_nonempty_document_scope():
    database = SQLiteStore(":memory:")
    database.initialize()
    run_store = RunStore(database)
    state = run_store.create(
        "gc-1",
        "live",
        task_id="task-original-empty",
        runtime_name="pi",
        agent_specs=[
            AgentProfile(
                agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
                primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
            ).model_dump(mode="json")
            for index in range(1, 4)
        ],
        task_context={
            "task_id": "task-original-empty",
            "data_space": "desensitized_real",
            "document_ids": [],
            "allowed_document_ids": [],
        },
    )
    task = ResearchTask(
        task_id="task-original-empty", group_chat_id="gc-1", title="研究任务",
        question="恢复时文档范围不能被扩大", document_ids=["doc-new"],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
        )
        for index in range(1, 4)
    ]
    runtime = MockRuntime()

    asyncio.run(engine.run_live_task_multi_agent(
        task, agents, store=database, run_store=run_store, state=state, runtime=runtime,
    ))

    assert runtime.invocations == []
    assert state.status == "failed"
    assert state.task_context["allowed_document_ids"] == []
    database.close()


def test_real_multi_agent_retry_replays_only_failed_agent_and_followers():
    database = SQLiteStore(":memory:")
    database.initialize()
    task = ResearchTask(
        task_id="task-retry", group_chat_id="gc-1", title="研究任务",
        question="资料中的强度趋势是什么？", document_ids=["doc-a"],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    agents = [
        AgentProfile(
            agent_id=f"agent-{index}", name=f"分析 Agent {index}", role="master_student",
            primary_ability="机制分析", allowed_data_spaces=["desensitized_real"],
            allowed_tools=["knowledge.search"],
        )
        for index in range(1, 4)
    ]
    failed_once = {"agent-2"}

    def result(invocation):
        if invocation.agent_id in failed_once:
            failed_once.remove(invocation.agent_id)
            return AgentResult(
                agent_id=invocation.agent_id, status="error", content="",
                error="temporary provider failure", data_space=invocation.data_space,
            )
        return AgentResult(
            agent_id=invocation.agent_id, status="ok", content=f"{invocation.agent_id} 候选",
            structured_output={
                "claim": f"{invocation.agent_id} 的资料判断",
                "evidence_refs": ["chunk-a"],
                "reasoning_summary": "只基于授权资料",
                "uncertainty": "仍需更多样本",
                "next_action": "补充对照实验",
            }, data_space=invocation.data_space,
        )

    runtime = MockRuntime(result_factory=result)
    state = asyncio.run(engine.run_live_task_multi_agent(
        task,
        agents,
        store=database,
        runtime=runtime,
        candidate_writer=lambda _state, invocation, _result: {
            "candidate_id": f"candidate-{invocation.agent_id}",
        },
    ))
    assert state.status == "failed"
    first_failed_invocation = runtime.invocations[-1].invocation_id

    store = RunStore(database)
    recovered = store.get(state.run_id)
    assert recovered is not None
    coordinator = MultiAgentRunCoordinator(
        store,
        None,
        runtime_factory=lambda **_: runtime,
        tool_registry=object(),
        context_factory=lambda _invocation: object(),
    )
    asyncio.run(coordinator.retry_agent(recovered.run_id, "agent-2"))

    assert [invocation.agent_id for invocation in runtime.invocations] == [
        "agent-1", "agent-2", "agent-2", "agent-3",
    ]
    assert runtime.invocations[2].attempt == 2
    assert runtime.invocations[2].retry_of == first_failed_invocation
    assert recovered.status == "awaiting_review"
    assert len([step for step in recovered.steps if step.actor == "agent-1" and step.kind == "candidate"]) == 1
    database.close()
