"""AgentProfile 声明式角色对象契约。

仅定义 Agent 的最小 Pydantic 校验模型：Agent 名称或标识、角色类型、
主能力、副能力、通用科研能力、允许的数据空间、允许的工具范围、
禁止动作摘要、专业范围与知识库覆盖范围声明。
不包含真实 Agent 执行器、system prompt 完整内容、LLM provider 配置
或权限拦截执行逻辑。
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from .common import AgentRole, DataSpace


class AgentProfile(BaseModel):
    """Agent 声明式角色对象：固定 Agent 角色、能力画像、工具范围与数据访问边界。

    表达 Agent 名称或标识、角色类型、主能力、副能力、通用科研能力、
    允许的数据空间、允许的工具范围、禁止动作摘要、专业范围与
    知识库覆盖范围声明；不表达真实 Agent 执行器、system prompt 完整内容、
    LLM provider 配置或权限拦截执行逻辑。
    """

    agent_id: str = ""  # 稳定 Agent 标识；demo 中映射自数据包 local_key
    name: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]  # Agent 展示名称
    role: AgentRole  # 角色类型
    description: str | None = None  # Agent 背景与职责说明
    primary_ability: str | None = None  # 主能力
    secondary_abilities: list[str] = Field(default_factory=list)  # 副能力
    general_research_abilities: list[str] = Field(default_factory=list)  # 通用科研能力
    allowed_data_spaces: list[DataSpace] = Field(default_factory=list)  # 允许的数据空间
    allowed_tools: list[str] = Field(default_factory=list)  # 允许的工具范围
    forbidden_actions: str | None = None  # 禁止动作摘要
    specialty_domain: str | None = None  # 专业范围
    knowledge_base_coverage: str | None = None  # 知识库覆盖范围声明
