"""Demo Agent 校验测试（Task 9）。

覆盖：existing 引用不存在 Agent id 或角色不匹配时抛出可映射为
422 的业务校验错误；demo_package_id 非法时保留 demo loader
的明确错误信息；校验通过时成员引用指向 demo `AgentProfile`。
"""

import pytest

from app.demo_data.loader import (
    DemoPackageInvalidIdError,
    DemoPackageNotFoundError,
    load_demo_package,
)
from app.demo_data.object_factory import build_agent_profiles
from app.agents import service as agents_service
from app.group_chats.creation_service import (
    AgentNotFoundError,
    AgentRoleMismatchError,
    validate_existing_agents,
)
from app.group_chats.schemas import (
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


def _selection(
    postdoc_ids: list[str] = ["agent-postdoc-1"],
    phd_ids: list[str] = ["agent-phd-1"],
    master_mode: SelectionMode = SelectionMode.GENERATE,
    master_ids: list[str] | None = None,
    master_count: int | None = 3,
) -> MemberSelection:
    return MemberSelection(
        postdoc=RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=postdoc_ids,
        ),
        phd_student=RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=phd_ids,
        ),
        master_student=RoleMemberSelection(
            selection_mode=master_mode,
            agent_ids=master_ids,
            count=master_count,
        ),
    )


def test_unknown_agent_id_raises_not_found() -> None:
    """existing 引用不存在的 Agent id 抛出 AgentNotFoundError（可映射 422）。"""
    selection = _selection(postdoc_ids=["agent-postdoc-999"])
    with pytest.raises(AgentNotFoundError, match="agent-postdoc-999"):
        validate_existing_agents(_PACKAGE, selection)


def test_role_mismatch_raises() -> None:
    """existing 引用角色不匹配的 Agent id 抛出 AgentRoleMismatchError（可映射 422）。"""
    # agent-postdoc-1 是 postdoc，放在 master_student 键下即角色不匹配。
    selection = _selection(
        postdoc_ids=["agent-ms-1"],
        master_mode=SelectionMode.EXISTING,
        master_ids=["agent-ms-1", "agent-ms-2", "agent-ms-3"],
    )
    with pytest.raises(AgentRoleMismatchError, match="agent-ms-1"):
        validate_existing_agents(_PACKAGE, selection)


def test_valid_selection_passes_validation() -> None:
    """合法 existing 引用通过校验，不抛异常。"""
    selection = _selection(
        master_mode=SelectionMode.EXISTING,
        master_ids=["agent-ms-1", "agent-ms-2", "agent-ms-3"],
    )
    validate_existing_agents(_PACKAGE, selection)


def test_invalid_package_id_keeps_loader_error() -> None:
    """demo_package_id 非法时保留 demo loader 的明确错误信息。"""
    with pytest.raises(DemoPackageInvalidIdError, match="package_id"):
        load_demo_package("../outside")


def test_unknown_package_keeps_loader_error() -> None:
    """未知 demo_package_id 时保留 loader 的路径信息。"""
    with pytest.raises(DemoPackageNotFoundError, match="no_such_package"):
        load_demo_package("no_such_package")


def test_business_errors_are_subclass_of_creation_error() -> None:
    """Agent 校验错误属于 GroupChatCreationError 家族，可统一映射 422。"""
    from app.group_chats.creation_service import GroupChatCreationError

    assert issubclass(AgentNotFoundError, GroupChatCreationError)
    assert issubclass(AgentRoleMismatchError, GroupChatCreationError)
