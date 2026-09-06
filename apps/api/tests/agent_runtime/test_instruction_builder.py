"""AgentInstruction must be an explicit, deterministic Runtime input."""

import asyncio
import importlib

from app.agent_runtime.legacy_llm_runtime import LegacyLLMRuntime
from app.agent_runtime.schemas import AgentInvocation
from app.domain.schemas import AgentProfile


def _profile() -> AgentProfile:
    return AgentProfile(
        agent_id="agent-a",
        name="证据 Agent",
        role="master_student",
        primary_ability="证据核查",
        secondary_abilities=["统计分析"],
        general_research_abilities=["文献检索"],
        allowed_data_spaces=["synthetic"],
        allowed_tools=["literature_search"],
        specialty_domain="材料表征",
        knowledge_base_coverage="孔结构与强度",
        forbidden_actions="不得批准正式结论",
    )


def test_builder_carries_every_profile_field_into_instruction() -> None:
    module = importlib.import_module("app.agent_runtime.instruction_builder")
    instruction = module.build_agent_instruction(
        _profile(),
        profile_version="v7",
        topic_context={"name": "泡沫混凝土", "summary": "孔结构课题"},
        task_context={"initial_intent": "找出强度变化原因"},
        phase="independent_analysis",
        output_contract="claim_four_fields",
    )

    assert instruction.profile_version == "v7"
    assert instruction.agent_id == "agent-a"
    assert instruction.role == "master_student"
    assert instruction.primary_ability == "证据核查"
    assert instruction.secondary_abilities == ["统计分析"]
    assert instruction.general_research_abilities == ["文献检索"]
    assert instruction.allowed_data_spaces == ["synthetic"]
    assert instruction.allowed_tools == ["literature_search"]
    assert instruction.specialty_domain == "材料表征"
    assert instruction.knowledge_base_coverage == "孔结构与强度"
    assert instruction.forbidden_actions == "不得批准正式结论"
    assert instruction.task_context["initial_intent"] == "找出强度变化原因"
    assert instruction.topic_context["name"] == "泡沫混凝土"
    assert instruction.phase == "independent_analysis"
    assert instruction.output_contract == "claim_four_fields"
    assert "证据核查" in instruction.render()
    assert "不得批准正式结论" in instruction.render()


def test_builder_is_deterministic_for_identical_inputs() -> None:
    module = importlib.import_module("app.agent_runtime.instruction_builder")
    kwargs = {
        "profile_version": "v7",
        "topic_context": {"name": "泡沫混凝土"},
        "task_context": {"initial_intent": "找出强度变化原因"},
        "phase": "independent_analysis",
        "output_contract": "claim_four_fields",
    }
    first = module.build_agent_instruction(_profile(), **kwargs)
    second = module.build_agent_instruction(_profile(), **kwargs)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_legacy_runtime_sends_instruction_as_system_message(monkeypatch) -> None:
    captured: dict[str, list[dict[str, str]]] = {}

    async def fake_chat(messages: list[dict[str, str]], **_kwargs: object) -> str:
        captured["messages"] = messages
        return "candidate"

    monkeypatch.setattr(
        "app.agent_runtime.legacy_llm_runtime.chat", fake_chat
    )
    invocation = AgentInvocation(
        agent_id="agent-a",
        role="master_student",
        task="分析任务",
        agent_instruction={
            "instruction_version": "agent-instruction-v1",
            "profile_version": "v7",
            "agent_id": "agent-a",
            "role": "master_student",
            "identity": "证据 Agent",
            "responsibilities": [],
            "primary_ability": "证据核查",
            "secondary_abilities": [],
            "general_research_abilities": [],
            "allowed_data_spaces": ["synthetic"],
            "allowed_tools": [],
            "specialty_domain": None,
            "knowledge_base_coverage": None,
            "forbidden_actions": "不得批准正式结论",
            "topic_context": {},
            "task_context": {},
            "phase": "independent_analysis",
            "phase_rules": [],
            "output_contract": "free_text",
            "safety_rules": [],
        },
    )

    result = asyncio.run(LegacyLLMRuntime().invoke(invocation))

    assert result.status == "ok"
    assert captured["messages"][0]["role"] == "system"
    assert "agent-a" in captured["messages"][0]["content"]
    assert captured["messages"][1] == {"role": "user", "content": "分析任务"}
