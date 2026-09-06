"""Build deterministic Runtime instructions from persisted Agent profiles."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.agent_runtime.schemas import AgentInstruction
from app.domain.schemas import AgentProfile


_ROLE_RESPONSIBILITIES: dict[str, list[str]] = {
    "master_student": [
        "独立形成候选观点",
        "明确证据边界、反例和可观察预测",
        "按审查意见逐条修订自己的 Markdown 研究产物",
    ],
    "phd_student": [
        "在组会前执行结构化质量审查",
        "指出反例、可推翻条件和缺失观察",
        "不得替硕士生成组会汇报或直接批准结论",
    ],
    "postdoc": [
        "仅在匹配的专业请求下提供范围内回答",
        "说明专业回答的依据、边界和限制",
    ],
    "group_meeting_secretary": [
        "整理组会材料和状态摘要",
        "记录来源和待决事项",
    ],
}


@dataclass(frozen=True)
class RoleInvocationPlan:
    """Deterministic execution plan for one role/phase pair."""

    role: str
    phase: str
    task: str
    output_contract: str
    allowed_tools: list[str]


_ROLE_PHASE_CONTRACTS: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {
    (
        "master_student",
        "independent_analysis",
    ): (
        "claim_four_fields",
        ("memory.query", "literature.search", "experiment.analyze_demo", "knowledge.search"),
    ),
    ("master_student", "revision"): (
        "revision_dispositions",
        ("memory.query", "knowledge.search"),
    ),
    ("phd_student", "review_gate"): ("review_gate", ()),
    ("postdoc", "postdoc_exchange"): ("postdoc_synthesis", ()),
}


class RoleInvocationBuilder:
    """Build role-specific prompt, contract and tool scope without side effects."""

    @staticmethod
    def build(role: str, phase: str, task_scope: dict) -> RoleInvocationPlan:
        normalized_role = str(role).strip()
        normalized_phase = str(phase).strip()
        contract = _ROLE_PHASE_CONTRACTS.get((normalized_role, normalized_phase))
        if contract is None:
            raise ValueError(f"unsupported role/phase: {normalized_role}/{normalized_phase}")

        requested_tools = task_scope.get("allowed_tools")
        data_space = str(task_scope.get("data_space", "synthetic")).strip()
        if not requested_tools:
            requested_tools = [
                name
                for name in contract[1]
                if not (data_space == "synthetic" and name == "knowledge.search")
                and not (data_space in {"real", "desensitized_real"} and name != "knowledge.search")
            ]
        if not isinstance(requested_tools, (list, tuple, set)):
            raise ValueError("task_scope.allowed_tools must be a sequence")
        permitted = set(contract[1])
        allowed_tools = []
        for tool in requested_tools:
            name = str(tool).strip()
            if name and name in permitted and name not in allowed_tools:
                if data_space == "synthetic" and name == "knowledge.search":
                    continue
                allowed_tools.append(name)

        base_task = str(task_scope.get("task", "")).strip()
        if not base_task:
            base_task = "完成当前 ForumMind 科研任务"
        if (normalized_role, normalized_phase) == ("master_student", "independent_analysis"):
            task = (
                f"{base_task}\n请独立形成候选观点，必须输出判断、适用边界、可观察预测和可推翻条件；"
                "要求观点必须实质不同，至少给出一个可观察的区分预测并说明其区分候选解释的方式；"
                "不得复述其他 Agent，也不得写入正式 Memory 或作 PI 决策。"
            )
        elif (normalized_role, normalized_phase) == ("master_student", "revision"):
            task = (
                f"{base_task}\n请逐条回应审查意见并给出 accept/reject 与理由；"
                "只返回修订候选，不得自行冻结观点或写入正式 Memory。"
            )
        elif (normalized_role, normalized_phase) == ("phd_student", "review_gate"):
            task = (
                f"{base_task}\n请执行组会前审查门，检查反例、可推翻条件和缺失观察；"
                "只能给出审查结果，不得替硕士汇报或作 PI 决策。"
            )
        else:
            task = (
                f"{base_task}\n请仅在授权专业范围内完成综合，说明依据、限制和未决问题；"
                "范围外必须拒答，不得代替 ForumMind 作 PI 决策。"
            )
        return RoleInvocationPlan(
            role=normalized_role,
            phase=normalized_phase,
            task=task,
            output_contract=contract[0],
            allowed_tools=allowed_tools,
        )


def _phase_rules(role: str, phase: str, output_contract: str) -> list[str]:
    rules = [f"当前阶段：{phase}", f"输出契约：{output_contract}"] if phase else []
    if (role, phase) == ("master_student", "independent_analysis"):
        rules.extend([
            "只形成自己的 Claim 候选，必须包含判断、边界、预测和可推翻条件",
            "不得冻结观点、写入正式 Memory、改变阶段或作 PI 决策",
        ])
    elif (role, phase) == ("phd_student", "review_gate"):
        rules.extend([
            "只能输出 counterexample、falsification_condition、missing_observation 三类审查项",
            "不得替硕士汇报，不得批准、驳回或改变 PI 决策",
        ])
    elif (role, phase) == ("master_student", "revision"):
        rules.extend([
            "只能逐条输出 review item 的 disposition 候选",
            "不得自行冻结或写入正式 Memory",
        ])
    elif role == "postdoc":
        rules.extend([
            "仅回答 specialty_domain 范围内且有专属知识源覆盖的请求",
            "范围外请求必须明确拒答，不得补写或猜测领域外结论",
        ])
    return rules


def _strings(values: Sequence[object]) -> list[str]:
    return [str(value) for value in values]


def build_agent_instruction(
    profile: AgentProfile,
    *,
    profile_version: str,
    topic_context: dict,
    task_context: dict,
    phase: str,
    allowed_tools: list[str] | None = None,
    output_contract: str,
) -> AgentInstruction:
    """Create an instruction without network, model, or persistence side effects."""
    role = str(profile.role.value if hasattr(profile.role, "value") else profile.role)
    tools = list(profile.allowed_tools if allowed_tools is None else allowed_tools)
    return AgentInstruction(
        profile_version=profile_version,
        agent_id=profile.agent_id,
        role=role,
        identity=profile.name,
        description=profile.description,
        responsibilities=list(_ROLE_RESPONSIBILITIES.get(role, [])),
        primary_ability=profile.primary_ability,
        secondary_abilities=list(profile.secondary_abilities),
        general_research_abilities=list(profile.general_research_abilities),
        allowed_data_spaces=_strings(profile.allowed_data_spaces),
        allowed_tools=tools,
        specialty_domain=profile.specialty_domain,
        knowledge_base_coverage=profile.knowledge_base_coverage,
        forbidden_actions=profile.forbidden_actions,
        topic_context=dict(topic_context),
        task_context=dict(task_context),
        phase=phase,
        phase_rules=_phase_rules(role, phase, output_contract),
        output_contract=output_contract,
        safety_rules=[
            "Runtime 只返回候选输出",
            "不得直接写入正式 Memory 或改变 PI 决策",
            "不得执行 formal_memory_write、stage_transition 或 commit_*",
        ],
    )
