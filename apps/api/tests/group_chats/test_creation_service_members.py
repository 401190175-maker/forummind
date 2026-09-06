"""成员解析服务测试（Task 8）。

覆盖：从成员选择构造 `ChatMember` 列表，existing 成员为 active 且
携带 demo AgentProfile 引用，generate 成员为 pending_generation 占位，
成员 id / 角色 / 展示名稳定，且不伪造真实 AgentProfile。
"""

from app.demo_data.loader import load_demo_package
from app.domain.schemas import AgentRole, ObjectType
from app.group_chats.creation_service import build_chat_members
from app.group_chats.schemas import (
    CreateGroupChatRequest,
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)

_PACKAGE = load_demo_package("foam_concrete_case")


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


def test_build_members_existing_and_generate() -> None:
    """1 博后 existing + 1 博士 existing + 3 硕士 generate 构造 5 个成员。"""
    members = build_chat_members(
        "gc-001", _request().member_selection, _PACKAGE
    )
    assert len(members) == 5


def test_existing_members_active_with_profile_ref() -> None:
    """existing 成员状态为 active，携带指向 demo AgentProfile 的引用。"""
    members = build_chat_members(
        "gc-001", _request().member_selection, _PACKAGE
    )
    postdoc = members[0]
    assert postdoc.status == "active"
    assert postdoc.selection_mode is SelectionMode.EXISTING
    assert postdoc.role is AgentRole.POSTDOC
    assert postdoc.agent_profile_ref is not None
    assert postdoc.agent_profile_ref.object_type is ObjectType.AGENT_PROFILE
    assert postdoc.agent_profile_ref.object_id == (
        "foam_concrete_case@0.1.0:agent_profile:agent-postdoc-1"
    )
    assert postdoc.display_name == "演示博士后 Agent"


def test_generate_members_pending_generation_without_profile() -> None:
    """generate 成员状态为 pending_generation，不携带真实 AgentProfile。"""
    members = build_chat_members(
        "gc-001", _request().member_selection, _PACKAGE
    )
    masters = [m for m in members if m.role is AgentRole.MASTER_STUDENT]
    assert len(masters) == 3
    for member in masters:
        assert member.status == "pending_generation"
        assert member.selection_mode is SelectionMode.GENERATE
        assert member.agent_profile_ref is None
    assert [m.display_name for m in masters] == [
        "待生成硕士 Agent 1",
        "待生成硕士 Agent 2",
        "待生成硕士 Agent 3",
    ]


def test_member_ids_are_stable_and_scoped() -> None:
    """成员 id 为请求级稳定 id：<group_chat_id>:<role_key>:<agent_id|gen-N>。"""
    members = build_chat_members(
        "gc-001", _request().member_selection, _PACKAGE
    )
    assert [m.id for m in members] == [
        "gc-001:postdoc:agent-postdoc-1",
        "gc-001:phd_student:agent-phd-1",
        "gc-001:master_student:gen-1",
        "gc-001:master_student:gen-2",
        "gc-001:master_student:gen-3",
    ]
    assert all(m.group_chat_id == "gc-001" for m in members)


def test_member_roles_match_selection_keys() -> None:
    """成员角色与选择角色键一一对应。"""
    members = build_chat_members(
        "gc-001", _request().member_selection, _PACKAGE
    )
    assert [m.role for m in members] == [
        AgentRole.POSTDOC,
        AgentRole.PHD_STUDENT,
        AgentRole.MASTER_STUDENT,
        AgentRole.MASTER_STUDENT,
        AgentRole.MASTER_STUDENT,
    ]


def test_build_members_is_deterministic() -> None:
    """同一请求重复构造得到同一成员集合。"""
    selection = _request().member_selection
    first = build_chat_members("gc-001", selection, _PACKAGE)
    second = build_chat_members("gc-001", selection, _PACKAGE)
    assert [m.model_dump() for m in first] == [m.model_dump() for m in second]


def test_all_generate_members() -> None:
    """全 generate 模式：1/1/3 全部为待生成占位。"""
    request = _request(
        postdoc=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=1),
        phd=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=1),
        master=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=3),
    )
    members = build_chat_members("gc-002", request.member_selection, _PACKAGE)
    assert len(members) == 5
    assert all(m.status == "pending_generation" for m in members)
    assert all(m.agent_profile_ref is None for m in members)
