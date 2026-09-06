"""创建课题组群聊 API 的 HTTP DTO（请求与响应契约）。

边界约定：

- 本模块只定义请求/响应 DTO，不导入 FastAPI，不注册路由，
  不访问文件系统、数据库或网络。
- 群聊相关结构第一版以 DTO 表达（design §2），后续持久化前
  再升级为正式 domain schema。
- 成员结构默认校验（至少 1 博后、1 博士、3 硕士）在
  `CreateGroupChatRequest` 上完成，不静默补齐成员。
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.domain.schemas import (
    AgentRole,
    DataSpace,
    ObjectLifecycleStatus,
    ObjectReference,
    Project,
    ResearchQuestion,
    ResearchState,
    Task,
)
from app.tasks.schemas import DatasetVersionRef

# 非空字符串：去除首尾空白后必须至少包含一个字符。
NonEmptyString = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

# 默认最低科研组成员结构（design §8）：至少 1 博后、1 博士、3 硕士。
MIN_POSTDOC_MEMBERS = 1
MIN_PHD_STUDENT_MEMBERS = 1
MIN_MASTER_STUDENT_MEMBERS = 3


class SelectionMode(StrEnum):
    """成员选择模式：选择已有 Agent 或智能生成占位。"""

    EXISTING = "existing"  # 选择已有 Agent
    GENERATE = "generate"  # 智能生成占位（本 API 不执行真实生成）


class GenerateProfile(BaseModel):
    """智能生成成员的期望配置（智能生成配置模块）。

    全可选字段：编辑了才传；缺省回退角色默认占位语义。
    """

    display_name: str | None = None  # 编辑名称（缺省用角色默认）
    primary_ability: str | None = None  # 主能力
    description: str | None = None  # 背景/描述
    secondary_abilities: list[str] = Field(default_factory=list)  # 副能力
    general_research_abilities: list[str] = Field(default_factory=list)  # 通用科研能力（Skills）
    allowed_tools: list[str] = Field(default_factory=list)  # Tools（空=默认文件+搜索）
    allowed_data_spaces: list[str] = Field(default_factory=list)  # 数据空间边界
    forbidden_actions: str | None = None  # 禁止动作摘要
    specialty_domain: str | None = None  # 专业范围
    knowledge_base_coverage: str | None = None  # 知识库覆盖范围


class RoleMemberSelection(BaseModel):
    """单个角色的成员选择：`existing` 提供 agent_ids，`generate` 提供 count。"""

    selection_mode: SelectionMode
    agent_ids: list[NonEmptyString] | None = None
    count: int | None = None
    generate_profiles: list[GenerateProfile] | None = None  # generate 期望配置（可选，向后兼容）

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> "RoleMemberSelection":
        """按 selection_mode 校验对应字段：existing 必须有非空 agent_ids；generate 必须有 count >= 1。"""
        if self.selection_mode is SelectionMode.EXISTING:
            if not self.agent_ids:
                raise ValueError(
                    "existing 模式必须提供非空 agent_ids（选择已有 Agent）"
                )
        elif self.selection_mode is SelectionMode.GENERATE:
            if self.count is None or self.count < 1:
                raise ValueError(
                    "generate 模式必须提供 count 且 count >= 1（智能生成占位数量）"
                )
        return self


class MemberSelection(BaseModel):
    """按角色分组的成员选择：postdoc / phd_student / master_student。"""

    postdoc: RoleMemberSelection
    phd_student: RoleMemberSelection
    master_student: RoleMemberSelection


class CreateGroupChatRequest(BaseModel):
    """`POST /group-chats` 请求体（design §5）。

    第一版不包含 `group_name`、顶层 `agent_ids` 或 `research_direction`
    字段：课题名称与概述由 `topic_name` / `topic_summary` 表达，
    成员结构由按角色分组的 `member_selection` 表达。
    """

    topic_name: NonEmptyString  # 课题名称（必填，非空）
    topic_summary: NonEmptyString  # 课题概述（必填，非空）
    member_selection: MemberSelection  # 成员选择（必填，含三个角色键）
    data_space: Literal[DataSpace.SYNTHETIC, DataSpace.REAL, DataSpace.DESENSITIZED_REAL] = DataSpace.DESENSITIZED_REAL
    demo_package_id: NonEmptyString = "foam_concrete_case"  # demo 数据包（默认泡沫混凝土案例）
    create_placeholder_tasks: bool = True  # 是否创建待分配任务占位（默认 true）

    @model_validator(mode="after")
    def _validate_default_member_structure(self) -> "CreateGroupChatRequest":
        """校验默认最低科研组成员结构，不足时给出可定位到角色的错误（design §8）。

        计数规则：`existing` 按有效 `agent_ids` 数量计数，
        `generate` 按 `count` 计数；不静默补齐成员，不执行 Agent 生成。
        """
        validate_default_member_structure(self.member_selection)
        return self


def _role_member_count(selection: RoleMemberSelection) -> int:
    """单个角色分组的成员数量：existing 按 agent_ids 计数，generate 按 count 计数。"""
    if selection.selection_mode is SelectionMode.EXISTING:
        return len(selection.agent_ids or [])
    return selection.count or 0


def validate_default_member_structure(member_selection: MemberSelection) -> None:
    """校验默认最低科研组成员结构（design §8），不足时抛出 ValueError。"""
    postdoc_count = _role_member_count(member_selection.postdoc)
    phd_count = _role_member_count(member_selection.phd_student)
    master_count = _role_member_count(member_selection.master_student)

    if postdoc_count < MIN_POSTDOC_MEMBERS:
        raise ValueError(
            f"成员结构不足: postdoc 至少需要 {MIN_POSTDOC_MEMBERS} 人，当前 {postdoc_count} 人"
        )
    if phd_count < MIN_PHD_STUDENT_MEMBERS:
        raise ValueError(
            f"成员结构不足: phd_student 至少需要 {MIN_PHD_STUDENT_MEMBERS} 人，当前 {phd_count} 人"
        )
    if master_count < MIN_MASTER_STUDENT_MEMBERS:
        raise ValueError(
            f"成员结构不足: master_student 至少需要 {MIN_MASTER_STUDENT_MEMBERS} 人，"
            f"当前 {master_count} 人"
        )


class ProjectPhase(StrEnum):
    """课题阶段（design §6）：创建后默认进入课题形成阶段。"""

    TOPIC_FORMATION = "topic_formation"  # 课题形成阶段
    EXPERIMENT_DESIGN = "experiment_design"  # 实验设计阶段
    RESULT_ANALYSIS = "result_analysis"  # 结果分析阶段
    OUTPUT_PRODUCTION = "output_production"  # 成果产出阶段


class ProjectGroupChat(BaseModel):
    """课题组群聊初始化对象（design §7）：可由 SQLite 恢复的工作台状态。"""

    id: NonEmptyString  # 群聊对象 ID（创建时生成，响应可持久化）
    type: Literal["project_group_chat"] = "project_group_chat"  # 对象类型固定
    topic_name: NonEmptyString  # 课题名称
    topic_summary: NonEmptyString  # 课题概述
    data_space: DataSpace = DataSpace.SYNTHETIC  # 数据空间
    member_refs: list[ObjectReference] = Field(default_factory=list)  # 已有 Agent 成员画像引用（generate 占位无画像，不产生引用）
    project_ref: ObjectReference | None = None  # 关联 Project 引用
    status: ObjectLifecycleStatus = ObjectLifecycleStatus.ACTIVE  # 群聊状态
    team_run_ref: ObjectReference | None = None  # 团队运行占位引用
    artifact_summary_ref: ObjectReference | None = None  # 产物摘要占位引用
    activity_summary_ref: ObjectReference | None = None  # 课题组动态占位引用
    project_phase: ProjectPhase = ProjectPhase.TOPIC_FORMATION  # 课题阶段


class ChatMember(BaseModel):
    """群聊成员（design §7）：已有 Agent 成员或待生成成员占位。"""

    id: NonEmptyString  # 成员 ID（请求级稳定 ID）
    group_chat_id: NonEmptyString  # 所属群聊 ID
    member_type: Literal["user", "agent"] = "agent"  # 成员类型
    role: AgentRole  # 科研角色
    selection_mode: SelectionMode  # 成员来源模式
    agent_profile_ref: ObjectReference | None = None  # 已有 Agent 的画像引用
    display_name: NonEmptyString  # 展示名称
    status: Literal["active", "pending_generation"]  # 成员状态
    generate_profile: GenerateProfile | None = None  # 智能生成期望配置（existing 恒 None）
    configuration_version: str | None = None  # 生成成员确认后的配置版本


class ChatMessage(BaseModel):
    """群聊消息（design §7）：本轮只表达初始化系统消息。"""

    id: NonEmptyString  # 消息 ID（请求级稳定 ID）
    group_chat_id: NonEmptyString  # 所属群聊 ID
    message_type: Literal["system"] = "system"  # 消息类型
    sender_type: Literal["system", "agent", "user"] = "system"  # 发送方类型
    content: NonEmptyString  # 消息内容
    attachment_refs: list[ObjectReference] = Field(default_factory=list)  # 附件引用


class MentionTarget(BaseModel):
    """`@` 对象（design §4.2）：全体、角色或具体成员。"""

    target_type: Literal["all", "role", "member"]  # 对象类型
    target_id: NonEmptyString  # 对象 ID（all 时固定 "all"）
    label: NonEmptyString  # 展示名


class CreateMessageRequest(BaseModel):
    """持久化群聊消息请求：普通消息或带 mention 的消息。"""

    content: NonEmptyString  # 消息内容（空内容 422）
    mention: MentionTarget | None = None  # 可选 `@` 对象
    sender_id: NonEmptyString | None = None
    task_id: NonEmptyString | None = None
    attachment_ids: list[NonEmptyString] = Field(default_factory=list)
    data_space: DataSpace = DataSpace.SYNTHETIC


ChatMessageKind = Literal[
    "text",
    "attachment",
    "clarification_question",
    "clarification_ready",
    "clarification_blocked",
    "meeting_schedule",
    "run_status",
    "candidate",
]


class ChatMessageRecord(BaseModel):
    """可恢复聊天消息记录；消息事实由服务端 SQLite 保存。"""

    id: NonEmptyString  # 消息 ID（稳定递增）
    group_chat_id: NonEmptyString  # 所属群聊 ID
    sender_type: Literal["user", "system", "agent"] = "user"  # 发送方类型
    sender_id: NonEmptyString | None = None
    content: NonEmptyString  # 消息内容
    mention: MentionTarget | None = None  # `@` 对象（普通消息为 None）
    task_id: NonEmptyString | None = None
    attachment_ids: list[NonEmptyString] = Field(default_factory=list)
    kind: ChatMessageKind = "text"
    payload: dict[str, object] = Field(default_factory=dict)
    reply_to_message_id: NonEmptyString | None = None
    created_at: float  # 创建时间戳
    data_space: DataSpace = DataSpace.SYNTHETIC


class TaskClarificationRequest(BaseModel):
    """`@` 触发的任务澄清请求（design §4.2、§5.3）。"""

    initial_intent: NonEmptyString  # 用户的任务意图
    mention: MentionTarget  # 被点名的全体 / 角色 / 成员
    source_message_id: NonEmptyString | None = None
    dataset_refs: list[DatasetVersionRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_dataset_refs(self) -> "TaskClarificationRequest":
        keys = [(item.dataset_id, item.version) for item in self.dataset_refs]
        if len(set(keys)) != len(keys):
            raise ValueError("dataset_refs must be unique")
        return self


class ClarificationTurn(BaseModel):
    """逐轮澄清中的一轮问题与用户回答。"""

    question_id: NonEmptyString
    question: NonEmptyString
    answer: NonEmptyString | None = None


class TaskClarificationAnswerRequest(BaseModel):
    """提交当前澄清问题的回答。"""

    answer: NonEmptyString
    source_message_id: NonEmptyString | None = None


class TaskClarificationResponse(BaseModel):
    """苏格拉底式任务澄清响应（design §4.2、§5.3）。

    只创建澄清会话，不启动 run；澄清内容是任务上下文，不是正式科研结论。
    """

    id: NonEmptyString  # 澄清会话 ID（稳定递增）
    group_chat_id: NonEmptyString  # 所属群聊 ID
    status: Literal["awaiting_answer", "ready_to_assign", "blocked"] = "awaiting_answer"
    clarifier: NonEmptyString  # 澄清者（@全体 为博士 Agent）
    question_id: NonEmptyString | None = None
    question: NonEmptyString | None = None
    question_number: int = Field(ge=1, le=7)
    max_questions: Literal[7] = 7
    turns: list[ClarificationTurn] = Field(default_factory=list)
    error: str = ""
    error_code: str = ""
    user_message: str = ""
    data_space: DataSpace = DataSpace.SYNTHETIC  # 固定 synthetic
    dataset_refs: list[DatasetVersionRef] = Field(default_factory=list)


class FormalTaskContext(BaseModel):
    """Confirmed task context produced from one clarification conversation."""

    clarification_id: NonEmptyString
    group_chat_id: NonEmptyString
    initial_intent: NonEmptyString
    turns: list[ClarificationTurn] = Field(default_factory=list)
    topic_name: NonEmptyString
    topic_summary: NonEmptyString
    mention: MentionTarget
    clarifier_agent_id: NonEmptyString
    confirmed_at: float
    data_space: DataSpace = DataSpace.SYNTHETIC
    dataset_refs: list[DatasetVersionRef] = Field(default_factory=list)


class GroupChatTopic(BaseModel):
    """群聊承载的课题信息（design §6）：课题名称、概述与关联科研对象引用。"""

    topic_name: NonEmptyString  # 课题名称
    topic_summary: NonEmptyString  # 课题概述
    project_ref: ObjectReference | None = None  # Project 引用
    research_question_ref: ObjectReference | None = None  # 初始 ResearchQuestion 引用
    research_state_ref: ObjectReference | None = None  # 初始 ResearchState 引用


class TeamRun(BaseModel):
    """团队运行入口状态占位（design §7）：创建后团队未启动、自动化关闭。"""

    id: NonEmptyString  # 运行占位 ID
    group_chat_id: NonEmptyString  # 所属群聊 ID
    status: Literal["not_started"] = "not_started"  # 固定未启动
    started_at: str | None = None  # 启动时间（未启动时为空）
    automation_enabled: Literal[False] = False  # 固定未启用自动化


class TeamArtifactSummary(BaseModel):
    """团队产物摘要占位（design §7）：只返回目录与命名规则，不创建真实文件。"""

    group_chat_id: NonEmptyString  # 所属群聊 ID
    folders: list[NonEmptyString] = Field(default_factory=list)  # 每个 Agent 一个文件夹 + 例会记录
    latest_files: list[NonEmptyString] = Field(default_factory=list)  # 无真实文件，默认空
    naming_rule: NonEmptyString  # 文件命名规则：日期 + 任务名 + Agent 名


class MemberStatusEntry(BaseModel):
    """团队成员状态条目（design §7）：默认空闲，待生成成员保持待配置状态。"""

    member_id: NonEmptyString  # 成员 ID
    display_name: NonEmptyString  # 展示名称
    status: Literal["idle", "working", "meeting_or_discussing", "pending_generation"]


class TeamStatusSummary(BaseModel):
    """团队成员状态摘要占位（design §7）：状态灯图例 + 成员状态列表。"""

    group_chat_id: NonEmptyString  # 所属群聊 ID
    member_statuses: list[MemberStatusEntry] = Field(default_factory=list)  # 成员状态
    legend: list[Literal["idle", "working", "meeting_or_discussing"]] = Field(
        default_factory=lambda: ["idle", "working", "meeting_or_discussing"]
    )  # 状态灯图例


class ProjectGroupActivitySummary(BaseModel):
    """课题组动态占位（design §7）：默认无新交付、无新讨论记录。"""

    group_chat_id: NonEmptyString  # 所属群聊 ID
    new_artifact_count: int = 0  # 新交付文件数，默认 0
    latest_artifact_refs: list[ObjectReference] = Field(default_factory=list)  # 最新交付引用
    has_new_discussion_records: bool = False  # 是否有新聊天室自由讨论记录，默认 false
    latest_discussion_refs: list[ObjectReference] = Field(default_factory=list)  # 最新讨论引用
    member_status_overview: NonEmptyString  # 成员状态概览
    project_phase: ProjectPhase = ProjectPhase.TOPIC_FORMATION  # 当前课题阶段


class CreateGroupChatResponse(BaseModel):
    """`POST /group-chats` 完整响应（design §6）。

    固定边界声明：`persistence = "sqlite"`、
    `agent_automation = "disabled"`、`group_chat.data_space = "synthetic"`。
    `placeholder_tasks` 只允许是待分配任务占位（可为空），不包含 Agent 执行结果。
    """

    group_chat: ProjectGroupChat  # 课题组群聊初始化对象
    topic: GroupChatTopic  # 课题信息与科研对象引用
    members: list[ChatMember]  # 群聊成员
    initial_messages: list[ChatMessage]  # 初始系统消息
    project: Project | None = None  # 可选关联 Project
    research_question: ResearchQuestion | None = None  # 可选初始 ResearchQuestion
    research_state: ResearchState | None = None  # 可选初始 ResearchState
    placeholder_tasks: list[Task] = Field(default_factory=list)  # 待分配任务占位
    team_run: TeamRun  # 团队运行入口占位（未启动）
    artifact_summary: TeamArtifactSummary  # 产物摘要占位（无真实文件）
    team_status: TeamStatusSummary  # 成员状态摘要占位
    activity_summary: ProjectGroupActivitySummary  # 课题组动态占位
    project_phase: ProjectPhase = ProjectPhase.TOPIC_FORMATION  # 当前课题阶段
    warnings: list[str] = Field(default_factory=list)  # 边界说明
    persistence: Literal["sqlite"] = "sqlite"  # 保存到本地 SQLite
    agent_automation: Literal["disabled"] = "disabled"  # 固定未执行 Agent
