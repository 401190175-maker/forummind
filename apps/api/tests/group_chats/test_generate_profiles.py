"""智能生成配置测试（generate_profiles 可选字段）。

覆盖：generate_profiles 传递（display_name/primary_ability 随成员、generate_profile 附着）、
existing 忽略 generate_profiles、长度不足 zip（缺槽位默认占位）、超出截断。
"""

import pytest

from app.agents import service as agents_service
from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import build_agent_profiles
from app.domain.schemas import AgentRole
from app.group_chats.creation_service import build_chat_members
from app.group_chats.schemas import (
    CreateGroupChatRequest,
    GenerateProfile,
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)

_PACKAGE = load_demo_package("foam_concrete_case")


@pytest.fixture(autouse=True)
def _seed_service_agents(monkeypatch):
    profiles = {
        profile.agent_id: profile
        for profile in build_agent_profiles(_PACKAGE)
    }
    monkeypatch.setattr(
        agents_service,
        "get_agent_record",
        lambda agent_id: (
            {
                "agent_id": agent_id,
                "profile": profiles[agent_id].model_dump(mode="json"),
                "enabled": True,
            }
            if agent_id in profiles
            else None
        ),
    )


def _request(
    postdoc: RoleMemberSelection = RoleMemberSelection(
        selection_mode=SelectionMode.EXISTING,
        agent_ids=["agent-postdoc-1"],
    ),
    phd: RoleMemberSelection = RoleMemberSelection(
        selection_mode=SelectionMode.EXISTING,
        agent_ids=["agent-phd-1"],
    ),
    master: RoleMemberSelection = RoleMemberSelection(
        selection_mode=SelectionMode.GENERATE,
        count=3,
    ),
) -> CreateGroupChatRequest:
    return CreateGroupChatRequest(
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        member_selection=MemberSelection(
            postdoc=postdoc,
            phd_student=phd,
            master_student=master,
        ),
    )


def _masters(request: CreateGroupChatRequest):
    members = build_chat_members("gc-001", request.member_selection, _PACKAGE)
    return [m for m in members if m.role is AgentRole.MASTER_STUDENT]


def test_generate_profiles_attached_to_members() -> None:
    """generate_profiles 随成员返回：display_name 用编辑名、generate_profile 附着。"""
    request = _request(
        master=RoleMemberSelection(
            selection_mode=SelectionMode.GENERATE,
            count=3,
            generate_profiles=[
                GenerateProfile(
                    display_name="硕士甲",
                    primary_ability="文献与机制分析",
                    description="独立文献研究者",
                ),
                GenerateProfile(display_name="硕士乙", primary_ability="实验与测试方法"),
                GenerateProfile(display_name="硕士丙", primary_ability="数据与证据分析"),
            ],
        )
    )
    masters = _masters(request)
    assert [m.display_name for m in masters] == ["硕士甲", "硕士乙", "硕士丙"]
    assert masters[0].generate_profile is not None
    assert masters[0].generate_profile.primary_ability == "文献与机制分析"
    assert masters[0].generate_profile.description == "独立文献研究者"
    assert masters[1].generate_profile.primary_ability == "实验与测试方法"
    assert masters[2].generate_profile.primary_ability == "数据与证据分析"
    assert all(m.status == "pending_generation" for m in masters)
    assert all(m.agent_profile_ref is None for m in masters)


def test_existing_ignores_generate_profiles() -> None:
    """existing 模式传 generate_profiles 被忽略：existing 成员 generate_profile 恒 None。"""
    request = _request(
        postdoc=RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=["agent-postdoc-1"],
            generate_profiles=[
                GenerateProfile(display_name="不应生效", primary_ability="不应生效")
            ],
        )
    )
    members = build_chat_members("gc-001", request.member_selection, _PACKAGE)
    postdoc = members[0]
    assert postdoc.selection_mode is SelectionMode.EXISTING
    assert postdoc.generate_profile is None
    assert postdoc.display_name != "不应生效"


def test_generate_profiles_shorter_than_count_falls_back() -> None:
    """generate_profiles 长度不足 count：缺槽位回退默认占位（display_name 默认、generate_profile None）。"""
    request = _request(
        master=RoleMemberSelection(
            selection_mode=SelectionMode.GENERATE,
            count=3,
            generate_profiles=[GenerateProfile(display_name="唯一自定义")],
        )
    )
    masters = _masters(request)
    assert masters[0].display_name == "唯一自定义"
    assert masters[0].generate_profile is not None
    assert masters[1].display_name == "待生成硕士 Agent 2"
    assert masters[1].generate_profile is None
    assert masters[2].display_name == "待生成硕士 Agent 3"
    assert masters[2].generate_profile is None


def test_generate_profiles_longer_than_count_truncated() -> None:
    """generate_profiles 超出 count：zip 截断，只取前 count 个。"""
    request = _request(
        master=RoleMemberSelection(
            selection_mode=SelectionMode.GENERATE,
            count=3,
            generate_profiles=[
                GenerateProfile(display_name="甲"),
                GenerateProfile(display_name="乙"),
                GenerateProfile(display_name="丙"),
                GenerateProfile(display_name="丁"),
            ],
        )
    )
    masters = _masters(request)
    assert len(masters) == 3
    assert [m.display_name for m in masters] == ["甲", "乙", "丙"]
    assert all(m.generate_profile is not None for m in masters)
