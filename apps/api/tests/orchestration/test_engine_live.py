"""run_live 测试：通过 Agent Runtime Adapter 顺序调用并保留失败状态。"""
import asyncio

from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.pi_runtime import PiRuntime
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.orchestration import engine
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario


_LIVE_SPECS = [
    {
        "agent_id": "agent-ms-1",
        "role": "master_student",
        "primary_ability": "文献与机制分析",
    },
    {
        "agent_id": "agent-ms-2",
        "role": "master_student",
        "primary_ability": "实验与测试方法",
    },
    {
        "agent_id": "agent-ms-3",
        "role": "master_student",
        "primary_ability": "数据与证据分析",
    },
]


def _new_live(runtime_name="mock"):
    store = RunStore()
    return store.create(
        "gc-1",
        "live",
        agent_specs=_LIVE_SPECS,
        review_agent_spec={
            "agent_id": "agent-phd-1",
            "name": "博士",
            "role": "phd_student",
            "primary_ability": "机理审查",
            "profile": {
                "agent_id": "agent-phd-1",
                "name": "博士",
                "role": "phd_student",
                "primary_ability": "机理审查",
            },
        },
        runtime_name=runtime_name,
    )


def _valid_result(invocation: AgentInvocation, content: str = "LLM 生成的判断") -> AgentResult:
    return AgentResult(
        agent_id=invocation.agent_id,
        status="ok",
        content=content,
        structured_output={
            "statement": content,
            "boundary": "低密度且浆体均匀的样品",
            "prediction": "大孔比例升高时抗压强度下降",
            "falsification_condition": "控制孔结构后强度差异消失",
        },
        data_space=invocation.data_space,
    )


def test_live_generates_claims(monkeypatch):
    def ok_result(invocation: AgentInvocation) -> AgentResult:
        if invocation.phase == "review_gate":
            return AgentResult(
                agent_id=invocation.agent_id,
                status="ok",
                content="质量门审查完成",
                structured_output={
                    "items": [
                        {"kind": "counterexample", "content": "反例"},
                        {"kind": "falsification_condition", "content": "可推翻条件"},
                        {"kind": "missing_observation", "content": "缺失观察"},
                    ]
                },
                data_space=invocation.data_space,
            )
        assert invocation.agent_id.startswith("agent-ms")
        assert invocation.role == "master_student"
        assert invocation.task  # prompt 已构造
        return _valid_result(invocation)

    fake = MockRuntime(result_factory=ok_result)
    monkeypatch.setattr(engine, "create_runtime", lambda: fake)
    state = _new_live()
    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))
    claims = [s for s in state.steps if s.kind == "claim"]
    assert len(claims) == 3
    assert all(s.payload.get("source") == "live" for s in claims)
    assert all(s.payload.get("runtime") == "mock" for s in claims)
    assert len(fake.invocations) == 4
    assert [invocation.phase for invocation in fake.invocations] == [
        "independent_analysis",
        "independent_analysis",
        "independent_analysis",
        "review_gate",
    ]
    assert state.phase == "meeting"
    assert any(s.phase == "review_gate" for s in state.steps)


def test_live_fails_on_runtime_error_without_scenario_claim(monkeypatch):
    def error_result(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(status="error", content="", warnings=["LLM 不可用"])

    fake = MockRuntime(result_factory=error_result)
    monkeypatch.setattr(engine, "create_runtime", lambda: fake)
    state = _new_live()
    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))
    claims = [s for s in state.steps if s.kind == "claim"]
    assert claims == []
    assert state.status == "failed"
    assert state.phase == "failed"
    failure = next(s for s in state.steps if s.kind == "invocation")
    assert failure.actor == "agent-ms-1"
    assert failure.payload["status"] == "error"
    assert failure.payload["error"] == "LLM 不可用"


def test_live_fails_when_result_data_space_mismatches(monkeypatch):
    def wrong_space_result(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="不应写入的真实空间候选",
            data_space="real",
        )

    fake = MockRuntime(result_factory=wrong_space_result)
    monkeypatch.setattr(engine, "create_runtime", lambda: fake)
    state = _new_live()
    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))
    claims = [s for s in state.steps if s.kind == "claim"]
    assert claims == []
    assert state.status == "failed"
    assert "data_space" in next(s for s in state.steps if s.kind == "invocation").content


def test_live_fails_when_claim_fields_are_missing(monkeypatch):
    def incomplete_result(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="不完整的候选观点",
            structured_output={
                "statement": "判断",
                "boundary": "边界",
                "prediction": "预测",
            },
            data_space=invocation.data_space,
        )

    fake = MockRuntime(result_factory=incomplete_result)
    monkeypatch.setattr(engine, "create_runtime", lambda: fake)
    state = _new_live()
    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    claims = [s for s in state.steps if s.kind == "claim"]
    assert claims == []
    assert state.status == "failed"
    assert "falsification_condition" in next(
        s for s in state.steps if s.kind == "invocation"
    ).content


def test_live_keeps_completed_claims_when_a_later_agent_fails(monkeypatch):
    calls = 0

    def first_ok_then_error(invocation: AgentInvocation) -> AgentResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _valid_result(invocation, content="第一个 Agent 的真实判断")
        return AgentResult(
            agent_id=invocation.agent_id,
            status="error",
            content="",
            error="第二个 Agent 调用失败",
        )

    fake = MockRuntime(result_factory=first_ok_then_error)
    monkeypatch.setattr(engine, "create_runtime", lambda: fake)
    state = _new_live()

    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    claims = [s for s in state.steps if s.kind == "claim"]
    assert [claim.actor for claim in claims] == ["agent-ms-1"]
    assert claims[0].payload["source"] == "live"
    assert state.status == "failed"
    assert state.phase == "failed"
    assert next(
        s for s in state.steps if s.kind == "invocation" and s.payload["status"] == "error"
    ).content == "第二个 Agent 调用失败"


def test_run_live_constructs_agent_invocation(monkeypatch):
    def ok_result(invocation: AgentInvocation) -> AgentResult:
        return _valid_result(invocation, content="c")

    fake = MockRuntime(result_factory=ok_result)
    monkeypatch.setattr(engine, "create_runtime", lambda: fake)
    state = _new_live()
    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))
    invocation = fake.invocations[0]
    assert invocation.run_id == state.run_id
    assert invocation.group_chat_id == "gc-1"
    assert invocation.cycle == 1
    assert invocation.phase == "independent_analysis"
    assert invocation.output_contract == "claim_four_fields"
    assert invocation.data_space == "synthetic"
    assert invocation.context["cycle"] == 1
    assert invocation.allowed_tools == []


def test_live_prompts_require_distinct_predictions_and_specific_debate_references(monkeypatch):
    fake = MockRuntime(result_factory=lambda invocation: _valid_result(invocation, content="c"))
    monkeypatch.setattr(engine, "create_runtime", lambda: fake)
    state = _new_live()

    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))

    master_tasks = [
        invocation.task
        for invocation in fake.invocations
        if invocation.phase == "independent_analysis"
    ]
    assert len(master_tasks) == 3
    assert all("不得复述其他 Agent" in task for task in master_tasks)
    assert all("至少给出一个可观察的区分预测" in task for task in master_tasks)


def test_run_live_does_not_call_chat_directly():
    """engine 模块不再直接导入 / 调用 app.llm.chat。"""
    import inspect

    source = inspect.getsource(engine)
    assert "from app.llm.provider import" not in source
    assert "await chat(" not in source


def test_live_pi_invocation_gets_server_tool_specs(monkeypatch):
    class FakePi:
        def __init__(self):
            self.requests = []

        async def invoke(self, request):
            self.requests.append(request)
            return {"type": "final", "agent_id": request["agent_id"], "content": "c", "structured_output": {
                "statement": "c", "boundary": "b", "prediction": "p", "falsification_condition": "f"
            }}

    fake_pi = FakePi()
    captured = {}

    def create_pi(**kwargs):
        captured.update(kwargs)
        kwargs.pop("runtime_name", None)
        return PiRuntime(fake_pi, **kwargs)

    monkeypatch.setattr(engine, "create_runtime", create_pi)
    state = _new_live(runtime_name="pi")
    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))
    assert captured["tool_registry"] is not None
    assert captured["context_factory"] is not None
    assert fake_pi.requests[0]["allowed_tools"] == ["memory.query", "literature.search", "experiment.analyze_demo"]
    assert [spec["name"] for spec in fake_pi.requests[0]["tool_specs"]] == [
        "memory.query", "literature.search", "experiment.analyze_demo"
    ]
