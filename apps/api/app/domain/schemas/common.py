"""跨对象共享的轻量枚举与值对象契约。

本模块仅承载对象标识、对象引用、版本元信息与共享枚举，
不作为数据库基类，不包含 ORM 字段，不负责审计日志写入。
通用字段不强制每个对象完全相同，避免建立过大的“万能基类”。
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, StringConstraints

# 对象唯一标识：非空字符串，作为对象 ID 的公共约束。
ObjectId = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class ObjectType(StrEnum):
    """领域对象类型：对象引用的类型判别字段。"""

    PROJECT = "project"
    RESEARCH_QUESTION = "research_question"
    AGENT_PROFILE = "agent_profile"
    TASK = "task"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    RESEARCH_STATE = "research_state"


class ObjectReference(BaseModel):
    """对象引用：指向特定领域对象。

    完整引用携带版本号；缺省版本时表示“当前”弱引用
    （例如 Project 指向当前 ResearchQuestion 时可不带版本）。
    """

    object_type: ObjectType
    object_id: ObjectId
    version: str | None = None


class VersionInfo(BaseModel):
    """版本元信息：对象自身版本号与上一版本引用。"""

    version: str
    previous_version_id: ObjectReference | None = None


class DataSpace(StrEnum):
    """数据空间类型：显式标记数据来源性质，防止合成数据伪装成真实数据。"""

    REAL = "real"  # 真实
    DESENSITIZED_REAL = "desensitized_real"  # 脱敏真实
    VERIFIABLE_PUBLIC = "verifiable_public"  # 可核查公开来源
    SYNTHETIC = "synthetic"  # 合成


class SourceType(StrEnum):
    """来源类型：Evidence 的来源种类。"""

    LITERATURE = "literature"  # 文献
    EXPERIMENT = "experiment"  # 实验
    PUBLIC = "public"  # 公开来源
    USER_UPLOADED = "user_uploaded"  # 用户上传资料
    SYNTHETIC_DEMO = "synthetic_demo"  # 合成 demo 材料


class VerificationStatus(StrEnum):
    """核查状态：Evidence 来源的可核查程度。"""

    LEAD = "lead"  # 线索（无法定位来源）
    PENDING = "pending"  # 待核查
    VERIFIED = "verified"  # 已核查
    REJECTED = "rejected"  # 被拒绝


class ObjectLifecycleStatus(StrEnum):
    """对象生命周期状态：通用对象生命周期。"""

    DRAFT = "draft"  # 草稿
    ACTIVE = "active"  # 生效/进行中
    COMPLETED = "completed"  # 已完成
    ARCHIVED = "archived"  # 已归档
    DELETED = "deleted"  # 已删除


class AgentRole(StrEnum):
    """Agent 角色类型：声明式角色建模，不表示真实权限执行。"""

    MASTER_STUDENT = "master_student"  # 硕士生
    PHD_STUDENT = "phd_student"  # 博士生
    POSTDOC = "postdoc"  # 博士后
    GROUP_MEETING_SECRETARY = "group_meeting_secretary"  # 组会秘书


class TaskStatus(StrEnum):
    """任务状态：科研工作单元的状态。"""

    PENDING = "pending"  # 待执行
    IN_PROGRESS = "in_progress"  # 进行中
    BLOCKED = "blocked"  # 受阻
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class ClaimStatus(StrEnum):
    """Claim 状态：候选科学主张的科研状态，不表示导师批准或最终结论。"""

    CANDIDATE = "candidate"  # 候选
    SUPPORTED = "supported"  # 被支持
    WEAKENED = "weakened"  # 被削弱
    UNDECIDABLE = "undecidable"  # 不可判别
    WITHDRAWN = "withdrawn"  # 撤回
