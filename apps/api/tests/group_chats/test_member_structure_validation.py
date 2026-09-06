"""默认成员结构校验测试（Task 4）。

覆盖：最低科研组成员结构（至少 1 博后、1 博士、3 硕士）、
existing 按 agent_ids 计数、generate 按 count 计数、
成员不足时 Pydantic 校验失败且错误信息定位到不足角色。
"""

import pytest
from pydantic import ValidationError

from app.group_chats.schemas import (
    CreateGroupChatRequest,
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)


def _member_selection(
    postdoc_mode: SelectionMode = SelectionMode.EXISTING,
    postdoc_ids: list[str] | None = ["agent-postdoc-001"],
    postdoc_count: int | None = None,
    phd_mode: SelectionMode = SelectionMode.EXISTING,
    phd_ids: list[str] | None = ["agent-phd-001"],
    phd_count: int | None = None,
    master_mode: SelectionMode = SelectionMode.GENERATE,
    master_ids: list[str] | None = None,
    master_count: int | None = 3,
) -> MemberSelection:
    """构造可配置的成员选择，默认满足最低结构（1/1/3）。"""
    return MemberSelection(
        postdoc=RoleMemberSelection(
            selection_mode=postdoc_mode,
            agent_ids=postdoc_ids,
            count=postdoc_count,
        ),
        phd_student=RoleMemberSelection(
            selection_mode=phd_mode,
            agent_ids=phd_ids,
            count=phd_count,
        ),
        master_student=RoleMemberSelection(
            selection_mode=master_mode,
            agent_ids=master_ids,
            count=master_count,
        ),
    )


def _request(member_selection: MemberSelection) -> CreateGroupChatRequest:
    return CreateGroupChatRequest(
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        member_selection=member_selection,
    )


def test_minimum_structure_existing_and_generate_passes() -> None:
    """1 博后 existing + 1 博士 existing + 3 硕士 generate 通过校验。"""
    request = _request(_member_selection())
    assert request.member_selection.master_student.count == 3


def test_master_students_generate_count_two_fails() -> None:
    """generate 模式硕士只有 2 人时校验失败，错误定位到 master_student。"""
    selection = _member_selection(master_count=2)
    with pytest.raises(ValidationError, match="master_student"):
        _request(selection)


def test_master_students_existing_two_ids_fails() -> None:
    """existing 模式硕士只有 2 个 agent_ids 时校验失败，错误定位到 master_student。"""
    selection = _member_selection(
        master_mode=SelectionMode.EXISTING,
        master_ids=["agent-ms-001", "agent-ms-002"],
    )
    with pytest.raises(ValidationError, match="master_student"):
        _request(selection)


def test_master_students_existing_three_ids_passes() -> None:
    """existing 模式硕士 3 个 agent_ids 时按数量计数通过校验。"""
    selection = _member_selection(
        master_mode=SelectionMode.EXISTING,
        master_ids=["agent-ms-001", "agent-ms-002", "agent-ms-003"],
    )
    request = _request(selection)
    assert request.member_selection.master_student.agent_ids == [
        "agent-ms-001",
        "agent-ms-002",
        "agent-ms-003",
    ]


def test_generate_master_count_three_passes() -> None:
    """generate 模式硕士 count=3 时按 count 计数通过校验。"""
    selection = _member_selection(master_mode=SelectionMode.GENERATE, master_count=3)
    request = _request(selection)
    assert request.member_selection.master_student.count == 3


def test_all_generate_structure_passes() -> None:
    """全 generate 模式 1/1/3 通过校验。"""
    selection = _member_selection(
        postdoc_mode=SelectionMode.GENERATE,
        postdoc_count=1,
        phd_mode=SelectionMode.GENERATE,
        phd_count=1,
        master_mode=SelectionMode.GENERATE,
        master_count=3,
    )
    request = _request(selection)
    assert request.member_selection.postdoc.count == 1
    assert request.member_selection.phd_student.count == 1
    assert request.member_selection.master_student.count == 3


def test_structure_validation_does_not_silently_fill() -> None:
    """校验不静默补齐成员：硕士不足时直接失败，不自动补到 3 人。"""
    selection = _member_selection(master_count=2)
    with pytest.raises(ValidationError):
        _request(selection)
