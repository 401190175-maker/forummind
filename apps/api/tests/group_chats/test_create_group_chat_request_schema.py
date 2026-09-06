"""创建课题组请求 DTO 测试（Task 3）。

覆盖：`CreateGroupChatRequest` 字段契约、必填与默认值、
不包含 group_name / 顶层 agent_ids / research_direction 字段。
"""

import pytest
from pydantic import ValidationError

from app.group_chats.schemas import (
    CreateGroupChatRequest,
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)
from app.domain.schemas import DataSpace


def _valid_member_selection() -> MemberSelection:
    """构造满足默认成员结构的最小成员选择：1 博后、1 博士、3 硕士。"""
    return MemberSelection(
        postdoc=RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=["agent-postdoc-001"],
        ),
        phd_student=RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=["agent-phd-001"],
        ),
        master_student=RoleMemberSelection(
            selection_mode=SelectionMode.GENERATE,
            count=3,
        ),
    )


def test_valid_request_with_defaults() -> None:
    """合法请求通过校验，demo_package_id 与 create_placeholder_tasks 使用默认值。"""
    request = CreateGroupChatRequest(
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        member_selection=_valid_member_selection(),
    )
    assert request.topic_name == "废弃泥浆基泡沫混凝土"
    assert request.topic_summary == "研究废弃泥浆基泡沫混凝土的机理与性能"
    assert request.data_space is DataSpace.DESENSITIZED_REAL
    assert request.demo_package_id == "foam_concrete_case"
    assert request.create_placeholder_tasks is True


def test_demo_package_id_override() -> None:
    """demo_package_id 可显式覆盖默认值。"""
    request = CreateGroupChatRequest(
        topic_name="课题A",
        topic_summary="概述A",
        member_selection=_valid_member_selection(),
        demo_package_id="other_case",
    )
    assert request.demo_package_id == "other_case"


def test_create_placeholder_tasks_false_accepted() -> None:
    """create_placeholder_tasks 可显式设为 false。"""
    request = CreateGroupChatRequest(
        topic_name="课题A",
        topic_summary="概述A",
        member_selection=_valid_member_selection(),
        create_placeholder_tasks=False,
    )
    assert request.create_placeholder_tasks is False


def test_topic_name_required() -> None:
    """缺少 topic_name 时校验失败。"""
    with pytest.raises(ValidationError):
        CreateGroupChatRequest(
            topic_summary="概述A",
            member_selection=_valid_member_selection(),
        )


def test_topic_name_blank_fails() -> None:
    """topic_name 为空白字符串时校验失败。"""
    with pytest.raises(ValidationError):
        CreateGroupChatRequest(
            topic_name="   ",
            topic_summary="概述A",
            member_selection=_valid_member_selection(),
        )


def test_topic_summary_required() -> None:
    """缺少 topic_summary 时校验失败。"""
    with pytest.raises(ValidationError):
        CreateGroupChatRequest(
            topic_name="课题A",
            member_selection=_valid_member_selection(),
        )


def test_topic_summary_blank_fails() -> None:
    """topic_summary 为空白字符串时校验失败。"""
    with pytest.raises(ValidationError):
        CreateGroupChatRequest(
            topic_name="课题A",
            topic_summary="  ",
            member_selection=_valid_member_selection(),
        )


def test_member_selection_required() -> None:
    """缺少 member_selection 时校验失败。"""
    with pytest.raises(ValidationError):
        CreateGroupChatRequest(
            topic_name="课题A",
            topic_summary="概述A",
        )


def test_member_selection_missing_role_key_fails() -> None:
    """member_selection 缺少任一角色键时校验失败。"""
    with pytest.raises(ValidationError):
        CreateGroupChatRequest(
            topic_name="课题A",
            topic_summary="概述A",
            member_selection={
                "postdoc": {"selection_mode": "existing", "agent_ids": ["a"]},
                "phd_student": {"selection_mode": "generate", "count": 1},
            },
        )


def test_request_has_no_group_name_or_flat_agent_ids_fields() -> None:
    """请求 DTO 不包含 group_name、顶层 agent_ids 或 research_direction 字段。"""
    fields = set(CreateGroupChatRequest.model_fields)
    assert fields == {
        "topic_name",
        "topic_summary",
        "member_selection",
        "data_space",
        "demo_package_id",
        "create_placeholder_tasks",
    }
    assert "group_name" not in fields
    assert "agent_ids" not in fields
    assert "research_direction" not in fields
