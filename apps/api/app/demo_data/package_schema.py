"""Demo 数据包自身的 Pydantic schema。

本模块定义静态 Demo 数据包的结构与基础语义校验模型，是
`demo_data/foam_concrete_case/package.json` 接口契约的 Pydantic 镜像：
顶层键与值域一一对应（package_id / version / label / synthetic_notice /
research_direction / literature_leads / experiment_constraints /
initial_anomaly / agent_profiles / initial_tasks / expected_initial_state /
reset_policy / integrity_rules）。

边界约定：

- 本模块自包含，不导入 `app.domain.schemas`（含枚举），
  受限字符串域使用 `typing.Literal` 表达，避免污染领域对象契约层。
- 本模块只负责数据包格式与基础语义校验；禁止性表述检查
  （如“已证实”“真实实验结果”等）由后续 integrity_guard 负责。
- 本模块不导入 FastAPI，不定义路由，不访问文件系统或数据库。
"""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

# 非空字符串：去除首尾空白后必须至少包含一个字符，用于全部必填文本字段。
NonEmptyString = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

# 文献线索状态：只能表达为线索（lead）或待核查材料（pending），
# 不允许标记为已核查（verified），与 VerificationStatus 的约束一致。
LiteratureLeadStatus = Literal["lead", "pending"]

# Agent 角色：与 AgentRole 枚举值一致（自包含表达，避免导入领域层）。
AgentRoleValue = Literal[
    "master_student",
    "phd_student",
    "postdoc",
    "group_meeting_secretary",
]

# 任务预期输出对象类型：与 ObjectType 枚举值一致。
ObjectTypeValue = Literal[
    "project",
    "research_question",
    "agent_profile",
    "task",
    "claim",
    "evidence",
    "research_state",
]

# 任务状态：与 TaskStatus 枚举值一致。
TaskStatusValue = Literal[
    "pending",
    "in_progress",
    "blocked",
    "completed",
    "cancelled",
]


class ResearchDirection(BaseModel):
    """研究方向：演示课题的标题、描述、材料体系、现象或目标与待解释事项。"""

    title: NonEmptyString  # 研究方向标题
    description: NonEmptyString  # 研究方向描述
    material_system: NonEmptyString  # 材料体系
    phenomenon_or_objective: NonEmptyString  # 现象或研究目标
    to_explain: list[str] = Field(min_length=1)  # 待解释事项（至少一项）


class LiteratureLead(BaseModel):
    """合成文献线索：只表达为线索或待核查材料，不是已核查证据。"""

    local_key: NonEmptyString  # 数据包内唯一键
    title: NonEmptyString  # 线索标题
    summary: NonEmptyString  # 线索摘要
    status: LiteratureLeadStatus  # 线索状态（lead / pending）
    note: NonEmptyString  # 备注（声明其为合成线索，仅作待核查材料）


class ExperimentConstraints(BaseModel):
    """实验约束：设备、周期、样品、成本、可测指标与安全边界。"""

    equipment: NonEmptyString  # 设备
    timeline: NonEmptyString  # 时间周期
    samples: NonEmptyString  # 样品说明
    cost: NonEmptyString  # 成本
    measurable_indicators: list[str] = Field(min_length=1)  # 可测指标（至少一项）
    safety_boundary: NonEmptyString  # 安全边界


class InitialAnomaly(BaseModel):
    """初始异常：合成异常描述，必须显式携带 synthetic anomaly 标记字段。"""

    local_key: NonEmptyString  # 数据包内唯一键
    title: NonEmptyString  # 异常标题
    description: NonEmptyString  # 异常描述
    is_synthetic_anomaly: bool  # 合成异常标记（字段存在性由本 schema 强制，语义真值由 integrity_guard 检查）
    not_experiment_result_note: NonEmptyString  # 非真实实验结论声明


class AgentProfile(BaseModel):
    """Demo 初始 Agent 画像：角色、主要能力与允许数据空间。"""

    local_key: NonEmptyString  # 数据包内唯一键
    name: NonEmptyString  # 展示名称
    role: AgentRoleValue  # Agent 角色
    primary_ability: NonEmptyString  # 主要能力
    allowed_data_spaces: list[str] = Field(min_length=1)  # 允许数据空间

    @model_validator(mode="after")
    def _allowed_data_spaces_include_synthetic(self) -> "AgentProfile":
        """允许数据空间必须包含 synthetic（include，不要求 exclusive）。"""
        if "synthetic" not in self.allowed_data_spaces:
            raise ValueError("Agent 允许数据空间必须包含 synthetic")
        return self


class InitialTask(BaseModel):
    """Demo 初始任务：描述、指派、预期输出对象类型、输入引用与状态。"""

    local_key: NonEmptyString  # 数据包内唯一键
    title: NonEmptyString  # 任务标题
    description: NonEmptyString  # 任务描述
    assigner: NonEmptyString  # 指派方（Agent local_key）
    assignee: NonEmptyString  # 执行方（Agent local_key）
    expected_output_object_type: ObjectTypeValue  # 预期输出对象类型
    input_local_keys: list[str] = Field(min_length=1)  # 输入对象 local_key 引用（至少一项）
    status: TaskStatusValue  # 任务状态


class ExpectedInitialState(BaseModel):
    """初始 ResearchState 摘要：关键证据引用与缺口、未决分歧说明。"""

    summary: NonEmptyString  # 初始状态摘要
    key_evidence_local_keys: list[str] = Field(min_length=1)  # 关键证据 local_key 引用（至少一项）
    evidence_gaps_summary: NonEmptyString  # 证据缺口说明
    unresolved_disagreements_summary: NonEmptyString  # 未决分歧说明


class ResetPolicy(BaseModel):
    """Reset 策略：reset 范围、确定性规则与允许数据空间。"""

    scope: NonEmptyString  # reset 范围
    determinism: NonEmptyString  # 确定性规则
    allowed_spaces: list[str] = Field(min_length=1)  # 允许数据空间

    @model_validator(mode="after")
    def _allowed_spaces_include_synthetic(self) -> "ResetPolicy":
        """允许数据空间必须包含 synthetic（include，不要求 exclusive）。"""
        if "synthetic" not in self.allowed_spaces:
            raise ValueError("Reset 允许数据空间必须包含 synthetic")
        return self


class DemoDataPackage(BaseModel):
    """Demo 数据包：静态数据包结构与基础语义校验模型。

    本模型是 `demo_data/foam_concrete_case/package.json` 的 Pydantic 镜像，
    顶层键与接口契约一一对应；不表达派生领域对象，不负责对象构造
    （object_factory）或合成数据完整性保护（integrity_guard）。
    """

    # 拒绝未知顶层键，保持接口契约紧凑。
    model_config = ConfigDict(extra="forbid")

    package_id: NonEmptyString  # 数据包唯一标识
    version: NonEmptyString  # 数据包版本
    label: NonEmptyString  # 人类可读名称
    synthetic_notice: NonEmptyString  # 合成声明（必须存在且非空）
    research_direction: ResearchDirection  # 研究方向
    literature_leads: list[LiteratureLead] = Field(min_length=1)  # 合成文献线索（至少一条）
    experiment_constraints: ExperimentConstraints  # 实验约束
    initial_anomaly: InitialAnomaly  # 初始异常描述
    agent_profiles: list[AgentProfile] = Field(min_length=1)  # Demo 初始 Agent 画像（至少一个）
    initial_tasks: list[InitialTask] = Field(min_length=1)  # Demo 初始任务（至少一个）
    expected_initial_state: ExpectedInitialState  # 初始状态摘要
    reset_policy: ResetPolicy  # Reset 策略
    integrity_rules: list[str] = Field(min_length=1)  # 数据包级完整性规则说明（至少一条）
