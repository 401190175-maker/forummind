import pytest

from app.group_chats import creation_service
from app.group_chats.creation_service import create_group_chat
from app.group_chats.schemas import (
    CreateGroupChatRequest,
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)


def _real_request() -> CreateGroupChatRequest:
    return CreateGroupChatRequest(
        topic_name="真实泡沫材料研究",
        topic_summary="使用上传资料研究孔结构与强度的关系",
        data_space="desensitized_real",
        member_selection=MemberSelection(
            postdoc=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=1),
            phd_student=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=1),
            master_student=RoleMemberSelection(selection_mode=SelectionMode.GENERATE, count=3),
        ),
    )


def test_real_workspace_does_not_load_demo_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_demo_is_loaded(_package_id: str):
        raise AssertionError("real workspace must not load foam_concrete_case")

    monkeypatch.setattr(creation_service, "load_demo_package", fail_if_demo_is_loaded)

    response = create_group_chat(_real_request())

    assert response.group_chat.data_space.value == "desensitized_real"
    assert response.project is None
    assert response.research_question is None
    assert response.research_state is None


def test_real_workspace_welcomes_from_postdoc_without_internal_space_label() -> None:
    response = create_group_chat(_real_request())

    assert response.initial_messages[0].sender_type == "agent"
    assert "数据空间" not in " ".join(
        message.content for message in response.initial_messages
    )
    assert "desensitized_real" not in " ".join(
        message.content for message in response.initial_messages
    )
