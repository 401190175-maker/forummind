"""`app.domain.schemas.agent_profile` 声明式角色对象契约测试。"""

import importlib

import pytest
from pydantic import ValidationError

from app.domain.schemas.agent_profile import AgentProfile
from app.domain.schemas.common import AgentRole, DataSpace


def test_module_is_importable() -> None:
    """`app.domain.schemas.agent_profile` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.agent_profile")
    assert module.__name__ == "app.domain.schemas.agent_profile"


def test_agent_profile_minimal_construction() -> None:
    """AgentProfile 可只凭名称与角色类型构造最小合法对象。"""
    profile = AgentProfile(
        name="组会秘书 Agent",
        role=AgentRole.GROUP_MEETING_SECRETARY,
    )
    assert profile.name == "组会秘书 Agent"
    assert profile.role is AgentRole.GROUP_MEETING_SECRETARY
    assert profile.primary_ability is None
    assert profile.secondary_abilities == []
    assert profile.general_research_abilities == []
    assert profile.allowed_data_spaces == []
    assert profile.allowed_tools == []
    assert profile.forbidden_actions is None
    assert profile.specialty_domain is None
    assert profile.knowledge_base_coverage is None


def test_agent_profile_expresses_full_semantics() -> None:
    """AgentProfile 完整表达名称、角色、能力、数据空间、工具、禁止动作、专业范围与知识库覆盖范围。"""
    profile = AgentProfile(
        name="泡沫混凝土博士后 Agent",
        role=AgentRole.POSTDOC,
        primary_ability="泡沫混凝土孔结构与性能关联分析",
        secondary_abilities=["文献综述", "实验数据整理"],
        general_research_abilities=["机理假设构建", "反例识别", "可验证预测"],
        allowed_data_spaces=[DataSpace.REAL, DataSpace.DESENSITIZED_REAL],
        allowed_tools=["文献检索", "数据统计分析"],
        forbidden_actions="不得批准真实实验、不得跨数据空间写入、不得代表导师裁决",
        specialty_domain="水泥基材料、泡沫混凝土",
        knowledge_base_coverage="课题组受治理的垂直领域知识库与公开文献库",
    )
    assert profile.name == "泡沫混凝土博士后 Agent"
    assert profile.role is AgentRole.POSTDOC
    assert profile.primary_ability == "泡沫混凝土孔结构与性能关联分析"
    assert profile.secondary_abilities == ["文献综述", "实验数据整理"]
    assert profile.general_research_abilities == ["机理假设构建", "反例识别", "可验证预测"]
    assert profile.allowed_data_spaces == [DataSpace.REAL, DataSpace.DESENSITIZED_REAL]
    assert profile.allowed_tools == ["文献检索", "数据统计分析"]
    assert profile.forbidden_actions == (
        "不得批准真实实验、不得跨数据空间写入、不得代表导师裁决"
    )
    assert profile.specialty_domain == "水泥基材料、泡沫混凝土"
    assert profile.knowledge_base_coverage == "课题组受治理的垂直领域知识库与公开文献库"


def test_postdoc_role_can_declare_specialty_and_knowledge_base_coverage() -> None:
    """博士后角色可以声明专业范围与知识库覆盖范围。"""
    profile = AgentProfile(
        name="博士后 Agent",
        role=AgentRole.POSTDOC,
        specialty_domain="水泥基材料",
        knowledge_base_coverage="课题组垂直领域知识库",
    )
    assert profile.role is AgentRole.POSTDOC
    assert profile.specialty_domain == "水泥基材料"
    assert profile.knowledge_base_coverage == "课题组垂直领域知识库"


def test_agent_profile_missing_role_raises() -> None:
    """AgentProfile 未定义角色类型时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        AgentProfile(name="硕士生 Agent")


def test_agent_profile_missing_name_raises() -> None:
    """AgentProfile 缺少名称或标识时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        AgentProfile(role=AgentRole.MASTER_STUDENT)


@pytest.mark.parametrize("name", ["", "   "])
def test_agent_profile_blank_name_raises(name: str) -> None:
    """AgentProfile 名称或标识不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        AgentProfile(name=name, role=AgentRole.MASTER_STUDENT)


@pytest.mark.parametrize("role", ["pi", "supervisor", "not-a-role"])
def test_agent_profile_invalid_role_raises(role: str) -> None:
    """AgentProfile 角色类型使用未定义值（含 PI/导师）时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        AgentProfile(name="硕士生 Agent", role=role)


def test_agent_profile_role_accepts_defined_value() -> None:
    """AgentProfile 角色类型接受已定义枚举值。"""
    profile = AgentProfile(name="博士生 Agent", role="phd_student")
    assert profile.role is AgentRole.PHD_STUDENT


@pytest.mark.parametrize("data_space", ["fake-space", "not-a-space"])
def test_agent_profile_invalid_allowed_data_space_raises(data_space: str) -> None:
    """AgentProfile 允许数据空间使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        AgentProfile(
            name="硕士生 Agent",
            role=AgentRole.MASTER_STUDENT,
            allowed_data_spaces=[data_space],
        )


def test_agent_profile_field_surface_avoids_forbidden_dimensions() -> None:
    """AgentProfile 只包含契约字段，不包含 system prompt、LLM provider、权限执行器或真实执行逻辑。"""
    assert set(AgentProfile.model_fields) == {
        "agent_id",
        "name",
        "role",
        "description",
        "primary_ability",
        "secondary_abilities",
        "general_research_abilities",
        "allowed_data_spaces",
        "allowed_tools",
        "forbidden_actions",
        "specialty_domain",
        "knowledge_base_coverage",
    }
