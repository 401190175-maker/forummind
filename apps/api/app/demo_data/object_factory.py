"""Demo 数据包对象工厂。

把已校验的 `DemoDataPackage` 映射为现有领域 schema 对象（设计 §2.5、§4.2）：

- `research_direction` → synthetic `Project` 与初始 `ResearchQuestion`。
- 对象 ID 采用确定性策略（设计 §4.3）：`package_id@version:object_type:local_key`，
  同一数据包版本重复构造得到同一对象集合与引用关系，不使用随机 UUID、
  当前时间或运行环境路径。

本模块只做内存对象构造，不访问网络、不访问数据库、不调用 LLM。
"""

from pydantic import BaseModel

from app.demo_data.loader import load_demo_package
from app.demo_data.package_schema import DemoDataPackage
from app.domain.schemas import (
    AgentProfile,
    AgentRole,
    DataSpace,
    Evidence,
    ObjectLifecycleStatus,
    ObjectReference,
    ObjectType,
    Project,
    ResearchQuestion,
    ResearchState,
    SourceType,
    Task,
    TaskStatus,
    VerificationStatus,
    VersionInfo,
)
from app.domain.schemas.evidence import DataCategory
from app.domain.schemas.project import ProjectConstraints

# 确定性 ID 的 local_key 常量：数据包内显式标识，保持构造可复现。
_PROJECT_LOCAL_KEY = "project"
_RESEARCH_QUESTION_LOCAL_KEY = "research_question"


def make_object_id(
    package: DemoDataPackage, object_type: ObjectType, local_key: str
) -> str:
    """按设计 §4.3 推导确定性对象 ID：`package_id@version:object_type:local_key`。

    同一数据包版本多次调用返回相同 ID；版本变化后允许生成新 ID，且可追踪。
    """
    return f"{package.package_id}@{package.version}:{object_type.value}:{local_key}"


def _project_ref(package: DemoDataPackage) -> ObjectReference:
    """构造指向 synthetic Project 的确定性对象引用。"""
    return ObjectReference(
        object_type=ObjectType.PROJECT,
        object_id=make_object_id(package, ObjectType.PROJECT, _PROJECT_LOCAL_KEY),
    )


def build_project(package: DemoDataPackage) -> Project:
    """把 `research_direction` 与 `experiment_constraints` 映射为 synthetic `Project`。

    `data_space` 固定为 `DataSpace.SYNTHETIC`（设计 §8.1），不依赖调用方传入。
    """
    direction = package.research_direction
    constraints = package.experiment_constraints
    return Project(
        title=direction.title,
        description=direction.description,
        data_space=DataSpace.SYNTHETIC,
        status=ObjectLifecycleStatus.ACTIVE,
        current_research_question=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id=make_object_id(
                package, ObjectType.RESEARCH_QUESTION, _RESEARCH_QUESTION_LOCAL_KEY
            ),
        ),
        constraints=ProjectConstraints(
            timeline=constraints.timeline,
            cost=constraints.cost,
            equipment=constraints.equipment,
            materials_scope=direction.material_system,
        ),
    )


def build_research_question(package: DemoDataPackage) -> ResearchQuestion:
    """把 `research_direction` 与 `experiment_constraints` 映射为初始 `ResearchQuestion`。

    表达现象或研究目标、材料体系、待解释事项、实验条件与现实约束，
    并通过确定性 `ObjectReference` 关联 synthetic Project。
    """
    direction = package.research_direction
    constraints = package.experiment_constraints
    return ResearchQuestion(
        phenomenon_or_objective=direction.phenomenon_or_objective,
        material_system=direction.material_system,
        to_explain=list(direction.to_explain),
        project=_project_ref(package),
        conditions=(
            f"设备：{constraints.equipment}；周期：{constraints.timeline}；"
            f"样品：{constraints.samples}"
        ),
        constraints=(
            f"成本：{constraints.cost}；可测指标："
            f"{'、'.join(constraints.measurable_indicators)}；"
            f"安全边界：{constraints.safety_boundary}"
        ),
    )


def agent_ref(package: DemoDataPackage, local_key: str) -> ObjectReference:
    """构造指向 demo `AgentProfile` 的确定性对象引用（按数据包内 local_key）。"""
    return ObjectReference(
        object_type=ObjectType.AGENT_PROFILE,
        object_id=make_object_id(package, ObjectType.AGENT_PROFILE, local_key),
    )


def build_agent_profiles(package: DemoDataPackage) -> list[AgentProfile]:
    """把数据包中的 Agent 画像映射为 demo `AgentProfile` 列表。

    只声明角色、能力与允许数据空间（设计 §4.2）；不包含 LLM provider、
    system prompt 执行逻辑或真实权限执行器。允许数据空间原样映射数据包
    声明值，schema 已保证包含 `synthetic`。
    """
    return [
        AgentProfile(
            agent_id=profile.local_key,
            name=profile.name,
            role=AgentRole(profile.role),
            primary_ability=profile.primary_ability,
            allowed_data_spaces=[
                DataSpace(space) for space in profile.allowed_data_spaces
            ],
        )
        for profile in package.agent_profiles
    ]


def evidence_ref(package: DemoDataPackage, local_key: str) -> ObjectReference:
    """构造指向 demo `Evidence` 的确定性对象引用（文献线索与初始异常共用 local_key 命名空间）。"""
    return ObjectReference(
        object_type=ObjectType.EVIDENCE,
        object_id=make_object_id(package, ObjectType.EVIDENCE, local_key),
    )


def build_initial_tasks(package: DemoDataPackage) -> list[Task]:
    """把数据包中的初始任务映射为 `Task` 列表。

    每个 Task 关联 synthetic Project，指派者/执行者使用确定性
    `AgentProfile` 引用，输入对象引用指向后续构造的 demo `Evidence`
    （文献线索或初始异常）；状态固定为待执行 `TaskStatus.PENDING`。
    """
    return [
        Task(
            title=task.title,
            description=task.description,
            project=_project_ref(package),
            expected_output_object_type=ObjectType(task.expected_output_object_type),
            status=TaskStatus(task.status),
            assigner=agent_ref(package, task.assigner),
            assignee=agent_ref(package, task.assignee),
            input_versions=[
                evidence_ref(package, local_key)
                for local_key in task.input_local_keys
            ],
        )
        for task in package.initial_tasks
    ]


def _package_source_location(
    package: DemoDataPackage, section: str, local_key: str
) -> str:
    """构造指向数据包内条目的确定性来源定位信息（合成材料的可追溯出处）。"""
    return (
        f"demo_data/{package.package_id}/package.json"
        f"#{section}[{local_key}]"
    )


def build_evidence(package: DemoDataPackage) -> list[Evidence]:
    """把文献线索与初始异常描述映射为 synthetic `Evidence` 列表。

    所有 demo Evidence 固定使用 `SourceType.SYNTHETIC_DEMO` 与
    `DataSpace.SYNTHETIC`（设计 §4.2、§8.1）；文献线索的核查状态只能是
    `VerificationStatus.LEAD` 或 `PENDING`，初始异常摘要保留合成异常语义，
    不写成真实实验结果。
    """
    material_system = package.research_direction.material_system
    evidence: list[Evidence] = []

    for lead in package.literature_leads:
        status = VerificationStatus(lead.status)
        evidence.append(
            Evidence(
                source_type=SourceType.SYNTHETIC_DEMO,
                data_category=DataCategory.TEXT,
                verification_status=status,
                applicability_boundary=(
                    f"合成文献线索（{lead.status}）：{lead.note or '仅限演示使用'}"
                ),
                project=_project_ref(package),
                source_location=_package_source_location(
                    package, "literature_leads", lead.local_key
                ),
                data_space=DataSpace.SYNTHETIC,
                materials=material_system,
                extraction_summary=lead.summary,
                pending_reason=(
                    "待核查（合成演示材料）" if status is VerificationStatus.PENDING else None
                ),
            )
        )

    anomaly = package.initial_anomaly
    evidence.append(
        Evidence(
            source_type=SourceType.SYNTHETIC_DEMO,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary=(
                anomaly.not_experiment_result_note
                or "本异常仅为演示而构造的合成异常描述，不代表任何真实实验结论"
            ),
            project=_project_ref(package),
            source_location=_package_source_location(
                package, "initial_anomaly", anomaly.local_key
            ),
            data_space=DataSpace.SYNTHETIC,
            materials=material_system,
            extraction_summary=anomaly.description,
            pending_reason="合成异常描述待核查（演示）",
        )
    )

    return evidence


class DemoObjectBundle(BaseModel):
    """确定性 demo 对象集合：一次 reset 的完整输出。

    汇总 synthetic `Project`、初始 `ResearchQuestion`、demo `AgentProfile`
    列表、初始 `Task` 列表、`Evidence` 列表与初始 synthetic `ResearchState`；
    同一数据包版本重建得到的对象、引用与序列化结果稳定一致。
    """

    package_id: str
    package_version: str
    project: Project
    research_question: ResearchQuestion
    agent_profiles: list[AgentProfile]
    tasks: list[Task]
    evidence: list[Evidence]
    research_state: ResearchState


def build_research_state(package: DemoDataPackage) -> ResearchState:
    """把数据包初始状态摘要映射为 synthetic `ResearchState`。

    引用初始 ResearchQuestion 与关键 Evidence（设计 §4.2），
    `data_space` 固定为 `DataSpace.SYNTHETIC`；快照版本取数据包版本，
    保持确定性。
    """
    state = package.expected_initial_state
    key_evidence_refs = [
        evidence_ref(package, local_key)
        for local_key in state.key_evidence_local_keys
    ]
    return ResearchState(
        project=_project_ref(package),
        current_research_question=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id=make_object_id(
                package, ObjectType.RESEARCH_QUESTION, _RESEARCH_QUESTION_LOCAL_KEY
            ),
        ),
        version=VersionInfo(version=package.version),
        data_space=DataSpace.SYNTHETIC,
        key_evidence=key_evidence_refs,
        evidence_gaps_summary=state.evidence_gaps_summary,
        unresolved_disagreements_summary=state.unresolved_disagreements_summary,
        input_versions=key_evidence_refs,
    )


def build_demo_objects(package: DemoDataPackage) -> DemoObjectBundle:
    """从已校验数据包构造完整确定性 demo 对象集合（设计 §2.5、§6.1）。"""
    return DemoObjectBundle(
        package_id=package.package_id,
        package_version=package.version,
        project=build_project(package),
        research_question=build_research_question(package),
        agent_profiles=build_agent_profiles(package),
        tasks=build_initial_tasks(package),
        evidence=build_evidence(package),
        research_state=build_research_state(package),
    )


def reset_demo_objects(package_id: str) -> DemoObjectBundle:
    """重新加载同一数据包版本并重建确定性对象集合（当前阶段 reset 语义）。

    reset 不删除文件、不写数据库、不修改全局状态；只是再次执行
    “加载 + 构造”流程，同一版本多次调用产生同一对象集合与引用关系。
    """
    package = load_demo_package(package_id)
    return build_demo_objects(package)
