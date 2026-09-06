"""Project 课题空间对象契约。

仅定义课题空间的最小 Pydantic 校验模型：课题标题与描述、数据空间、
课题状态、当前 ResearchQuestion / ResearchState 引用、关联 AgentProfile
引用与约束摘要。不包含数据库租户隔离、文件权限执行或 Memory 时间线字段。
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from .common import DataSpace, ObjectLifecycleStatus, ObjectReference


class ProjectConstraints(BaseModel):
    """约束摘要：课题的周期、成本、设备与材料范围等约束的文本摘要。"""

    timeline: str | None = None  # 周期
    cost: str | None = None  # 成本
    equipment: str | None = None  # 设备
    materials_scope: str | None = None  # 材料范围


class Project(BaseModel):
    """课题空间对象：隔离资料、角色、Memory 与状态的最小契约。

    表达课题标题与描述、数据空间、课题状态、当前 ResearchQuestion 引用、
    当前 ResearchState 引用、关联 AgentProfile 引用与约束摘要；
    不表达数据库租户隔离、文件访问权限执行或完整 Memory 时间线。
    """

    title: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
    description: str | None = None
    data_space: DataSpace
    status: ObjectLifecycleStatus
    current_research_question: ObjectReference | None = None
    current_research_state: ObjectReference | None = None
    agent_profiles: list[ObjectReference] = Field(default_factory=list)
    constraints: ProjectConstraints | None = None
