"""课题组群聊响应核心 DTO 测试（Task 5）。

覆盖：`ProjectGroupChat`、`ChatMember`、`ChatMessage`、`GroupChatTopic`
的字段契约与固定语义（type、status、data_space 等）。
"""

from app.domain.schemas import AgentRole, DataSpace, ObjectReference, ObjectType
from app.group_chats.schemas import (
    ChatMember,
    ChatMessage,
    GroupChatTopic,
    ProjectGroupChat,
    SelectionMode,
)

_AGENT_REF = ObjectReference(
    object_type=ObjectType.AGENT_PROFILE,
    object_id="foam_concrete_case@0.1.0:agent_profile:agent-postdoc-1",
)
_PROJECT_REF = ObjectReference(
    object_type=ObjectType.PROJECT,
    object_id="foam_concrete_case@0.1.0:project:project",
)
_QUESTION_REF = ObjectReference(
    object_type=ObjectType.RESEARCH_QUESTION,
    object_id="foam_concrete_case@0.1.0:research_question:research_question",
)
_STATE_REF = ObjectReference(
    object_type=ObjectType.RESEARCH_STATE,
    object_id="foam_concrete_case@0.1.0:research_state:research_state",
)


def test_project_group_chat_fields_and_fixed_semantics() -> None:
    """ProjectGroupChat 包含全部设计字段，type 固定为 project_group_chat。"""
    chat = ProjectGroupChat(
        id="gc-001",
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        member_refs=[_AGENT_REF],
        project_ref=_PROJECT_REF,
        team_run_ref=_AGENT_REF,
        artifact_summary_ref=_AGENT_REF,
        activity_summary_ref=_AGENT_REF,
    )
    assert chat.type == "project_group_chat"
    assert chat.data_space is DataSpace.SYNTHETIC
    assert chat.status.value == "active"
    assert chat.project_phase.value == "topic_formation"
    assert chat.member_refs == [_AGENT_REF]
    assert chat.project_ref == _PROJECT_REF


def test_project_group_chat_field_names() -> None:
    """ProjectGroupChat 字段名与设计一致。"""
    assert set(ProjectGroupChat.model_fields) == {
        "id",
        "type",
        "topic_name",
        "topic_summary",
        "data_space",
        "member_refs",
        "project_ref",
        "status",
        "team_run_ref",
        "artifact_summary_ref",
        "activity_summary_ref",
        "project_phase",
    }


def test_chat_member_active_existing() -> None:
    """existing 模式成员状态为 active 且携带 agent_profile_ref。"""
    member = ChatMember(
        id="gc-001:postdoc:agent-postdoc-1",
        group_chat_id="gc-001",
        role=AgentRole.POSTDOC,
        selection_mode=SelectionMode.EXISTING,
        agent_profile_ref=_AGENT_REF,
        display_name="演示博士后 Agent",
        status="active",
    )
    assert member.status == "active"
    assert member.agent_profile_ref == _AGENT_REF
    assert member.role is AgentRole.POSTDOC


def test_chat_member_pending_generation() -> None:
    """generate 模式成员状态为 pending_generation，不携带真实 Agent 画像。"""
    member = ChatMember(
        id="gc-001:master_student:gen-1",
        group_chat_id="gc-001",
        role=AgentRole.MASTER_STUDENT,
        selection_mode=SelectionMode.GENERATE,
        display_name="待生成硕士生 Agent 1",
        status="pending_generation",
    )
    assert member.status == "pending_generation"
    assert member.agent_profile_ref is None


def test_chat_member_status_values() -> None:
    """ChatMember.status 至少支持 active 和 pending_generation。"""
    assert set(ChatMember.model_fields["status"].annotation.__args__) == {
        "active",
        "pending_generation",
    }


def test_chat_message_fields() -> None:
    """ChatMessage 包含设计字段，默认为系统消息、无附件。"""
    message = ChatMessage(
        id="gc-001:msg-1",
        group_chat_id="gc-001",
        content="课题组已创建",
    )
    assert message.message_type == "system"
    assert message.sender_type == "system"
    assert message.attachment_refs == []


def test_chat_message_field_names() -> None:
    """ChatMessage 字段名与设计一致。"""
    assert set(ChatMessage.model_fields) == {
        "id",
        "group_chat_id",
        "message_type",
        "sender_type",
        "content",
        "attachment_refs",
    }


def test_group_chat_topic_fields() -> None:
    """GroupChatTopic 能表达课题名称、概述与科研对象引用。"""
    topic = GroupChatTopic(
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        project_ref=_PROJECT_REF,
        research_question_ref=_QUESTION_REF,
        research_state_ref=_STATE_REF,
    )
    assert topic.project_ref == _PROJECT_REF
    assert topic.research_question_ref == _QUESTION_REF
    assert topic.research_state_ref == _STATE_REF
