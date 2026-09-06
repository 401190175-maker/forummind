"""科研对象 Schema 契约层。

仅承载 Pydantic 校验模型与共享契约，不包含 ORM、
数据库连接、Repository、API route 或 Agent 执行逻辑。
本模块只做导出聚合：统一再导出七类核心对象与跨对象共享的
枚举和值对象，供后续模块从稳定入口导入。
"""

from .agent_profile import AgentProfile
from .claim import Claim
from .common import (
    AgentRole,
    ClaimStatus,
    DataSpace,
    ObjectId,
    ObjectLifecycleStatus,
    ObjectReference,
    ObjectType,
    SourceType,
    TaskStatus,
    VerificationStatus,
    VersionInfo,
)
from .evidence import Evidence
from .project import Project
from .research_question import ResearchQuestion
from .research_state import ResearchState
from .task import Task

__all__ = [
    # 七类核心对象
    "Project",
    "ResearchQuestion",
    "AgentProfile",
    "Task",
    "Claim",
    "Evidence",
    "ResearchState",
    # 共享枚举与值对象（来自 common.py）
    "ObjectId",
    "ObjectType",
    "ObjectReference",
    "VersionInfo",
    "DataSpace",
    "SourceType",
    "VerificationStatus",
    "ObjectLifecycleStatus",
    "AgentRole",
    "TaskStatus",
    "ClaimStatus",
]
