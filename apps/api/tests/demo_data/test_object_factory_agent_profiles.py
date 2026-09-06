"""`app.demo_data.object_factory` AgentProfile 构造测试。

覆盖：数据包 Agent 画像到 `AgentProfile` 的映射、角色枚举、
synthetic 数据访问边界与确定性引用。
"""

import importlib

from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import agent_ref, build_agent_profiles
from app.domain.schemas import AgentProfile, AgentRole, DataSpace, ObjectType


def test_module_is_importable() -> None:
    """`app.demo_data.object_factory` 可被导入。"""
    module = importlib.import_module("app.demo_data.object_factory")
    assert module.__name__ == "app.demo_data.object_factory"


def test_build_agent_profiles_maps_each_package_profile() -> None:
    """数据包内每个 Agent 画像都映射为一个 AgentProfile，数量一致。"""
    package = load_demo_package("foam_concrete_case")
    profiles = build_agent_profiles(package)
    assert len(profiles) == len(package.agent_profiles)
    assert all(isinstance(profile, AgentProfile) for profile in profiles)
    assert [profile.name for profile in profiles] == [
        spec.name for spec in package.agent_profiles
    ]


def test_default_demo_seed_contains_one_postdoc_one_phd_and_three_masters() -> None:
    package = load_demo_package("foam_concrete_case")
    profiles = build_agent_profiles(package)

    assert len(profiles) == 5
    assert [profile.agent_id for profile in profiles] == [
        "agent-ms-1",
        "agent-ms-2",
        "agent-ms-3",
        "agent-phd-1",
        "agent-postdoc-1",
    ]


def test_build_agent_profiles_preserves_local_key_as_agent_id() -> None:
    """已有 Agent 的选择标识必须稳定且彼此不同，不能返回 undefined。"""
    package = load_demo_package("foam_concrete_case")
    profiles = build_agent_profiles(package)
    assert [profile.agent_id for profile in profiles] == [
        spec.local_key for spec in package.agent_profiles
    ]
    assert len({profile.agent_id for profile in profiles}) == len(profiles)


def test_agent_profiles_use_agent_role_enum() -> None:
    """每个 AgentProfile 使用现有 AgentRole 枚举，且与数据包声明一致。"""
    package = load_demo_package("foam_concrete_case")
    profiles = build_agent_profiles(package)
    for profile, spec in zip(profiles, package.agent_profiles):
        assert isinstance(profile.role, AgentRole)
        assert profile.role.value == spec.role


def test_agent_profiles_allow_synthetic_space() -> None:
    """每个 AgentProfile 的允许数据空间包含 DataSpace.SYNTHETIC。"""
    package = load_demo_package("foam_concrete_case")
    profiles = build_agent_profiles(package)
    assert len(profiles) > 0
    for profile in profiles:
        assert DataSpace.SYNTHETIC in profile.allowed_data_spaces


def test_agent_profiles_carry_no_execution_dimensions() -> None:
    """AgentProfile 不携带 LLM provider、system prompt 或真实权限执行器字段。"""
    package = load_demo_package("foam_concrete_case")
    profiles = build_agent_profiles(package)
    for profile in profiles:
        assert profile.allowed_tools == []
        assert profile.forbidden_actions is None
        assert profile.specialty_domain is None
        assert profile.knowledge_base_coverage is None


def test_agent_ref_deterministic_and_typed() -> None:
    """AgentProfile 对象引用确定性稳定，且类型为 AGENT_PROFILE。"""
    package = load_demo_package("foam_concrete_case")
    first = agent_ref(package, "agent-ms-1")
    second = agent_ref(package, "agent-ms-1")
    assert first == second
    assert first.object_type is ObjectType.AGENT_PROFILE
    assert first.object_id.endswith(":agent_profile:agent-ms-1")


def test_agent_profiles_stable_across_repeated_construction() -> None:
    """同一数据包版本重复构造时 AgentProfile 列表与引用稳定不变。"""
    package = load_demo_package("foam_concrete_case")
    first = [profile.model_dump() for profile in build_agent_profiles(package)]
    second = [profile.model_dump() for profile in build_agent_profiles(package)]
    assert first == second
