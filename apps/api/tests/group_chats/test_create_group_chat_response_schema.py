"""创建课题组完整响应 DTO 测试（Task 7）。

覆盖：`CreateGroupChatResponse` 字段契约、固定边界声明
（not_persisted / disabled / synthetic）、默认课题阶段与
空任务占位，以及内嵌领域科研对象。
"""

import pytest
from pydantic import ValidationError

from app.domain.schemas import (
    AgentRole,
    DataSpace,
    ObjectLifecycleStatus,
    ObjectReference,
    ObjectType,
    Project,
    ResearchQuestion,
    ResearchState,
    Task,
    TaskStatus,
    VersionInfo,
)
from app.domain.schemas.project import ProjectConstraints
from app.group_chats.schemas import (
    ChatMember,
    ChatMessage,
    CreateGroupChatResponse,
    GroupChatTopic,
    MemberStatusEntry,
    ProjectGroupActivitySummary,
    ProjectGroupChat,
    ProjectPhase,
    SelectionMode,
    TeamArtifactSummary,
    TeamRun,
    TeamStatusSummary,
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


def _chat() -> ProjectGroupChat:
    return ProjectGroupChat(
        id="gc-001",
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        member_refs=[_AGENT_REF],
        project_ref=_PROJECT_REF,
    )


def _member() -> ChatMember:
    return ChatMember(
        id="gc-001:postdoc:agent-postdoc-1",
        group_chat_id="gc-001",
        role=AgentRole.POSTDOC,
        selection_mode=SelectionMode.EXISTING,
        agent_profile_ref=_AGENT_REF,
        display_name="演示博士后 Agent",
        status="active",
    )


def _message() -> ChatMessage:
    return ChatMessage(
        id="gc-001:msg-1",
        group_chat_id="gc-001",
        content="课题组已创建",
    )


def _topic() -> GroupChatTopic:
    return GroupChatTopic(
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        project_ref=_PROJECT_REF,
        research_question_ref=_QUESTION_REF,
        research_state_ref=_STATE_REF,
    )


def _project() -> Project:
    return Project(
        title="废弃泥浆基泡沫混凝土",
        description="研究废弃泥浆基泡沫混凝土的机理与性能",
        data_space=DataSpace.SYNTHETIC,
        status=ObjectLifecycleStatus.ACTIVE,
        current_research_question=_QUESTION_REF,
        constraints=ProjectConstraints(timeline="3 个月"),
    )


def _question() -> ResearchQuestion:
    return ResearchQuestion(
        phenomenon_or_objective="解释废弃泥浆基泡沫混凝土的强度发展现象",
        material_system="废弃泥浆基泡沫混凝土",
        to_explain=["强度形成机理"],
        project=_PROJECT_REF,
    )


def _state() -> ResearchState:
    return ResearchState(
        project=_PROJECT_REF,
        current_research_question=_QUESTION_REF,
        version=VersionInfo(version="0.1.0"),
        data_space=DataSpace.SYNTHETIC,
    )


def _task() -> Task:
    return Task(
        title="整理合成文献线索清单",
        project=_PROJECT_REF,
        expected_output_object_type=ObjectType.EVIDENCE,
        status=TaskStatus.PENDING,
    )


def _team_run() -> TeamRun:
    return TeamRun(id="gc-001:team-run", group_chat_id="gc-001")


def _artifact_summary() -> TeamArtifactSummary:
    return TeamArtifactSummary(
        group_chat_id="gc-001",
        folders=["agent-postdoc-1", "例会记录"],
        naming_rule="日期 + 任务名 + Agent 名",
    )


def _team_status() -> TeamStatusSummary:
    return TeamStatusSummary(
        group_chat_id="gc-001",
        member_statuses=[
            MemberStatusEntry(
                member_id="gc-001:postdoc:agent-postdoc-1",
                display_name="演示博士后 Agent",
                status="idle",
            )
        ],
    )


def _activity_summary() -> ProjectGroupActivitySummary:
    return ProjectGroupActivitySummary(
        group_chat_id="gc-001",
        member_status_overview="成员全部空闲",
    )


def _response(**overrides) -> CreateGroupChatResponse:
    """构造合法完整响应，可通过 overrides 覆盖字段。"""
    data = dict(
        group_chat=_chat(),
        topic=_topic(),
        members=[_member()],
        initial_messages=[_message()],
        project=_project(),
        research_question=_question(),
        research_state=_state(),
        placeholder_tasks=[_task()],
        team_run=_team_run(),
        artifact_summary=_artifact_summary(),
        team_status=_team_status(),
        activity_summary=_activity_summary(),
    )
    data.update(overrides)
    return CreateGroupChatResponse(**data)


def test_response_field_names() -> None:
    """CreateGroupChatResponse 字段与设计一致。"""
    assert set(CreateGroupChatResponse.model_fields) == {
        "group_chat",
        "topic",
        "members",
        "initial_messages",
        "project",
        "research_question",
        "research_state",
        "placeholder_tasks",
        "team_run",
        "artifact_summary",
        "team_status",
        "activity_summary",
        "project_phase",
        "warnings",
        "persistence",
        "agent_automation",
    }


def test_response_fixed_boundary_declarations() -> None:
    """响应固定声明：sqlite / disabled / synthetic / topic_formation。"""
    response = _response()
    assert response.persistence == "sqlite"
    assert response.agent_automation == "disabled"
    assert response.group_chat.data_space is DataSpace.SYNTHETIC
    assert response.project_phase is ProjectPhase.TOPIC_FORMATION


def test_response_persistence_cannot_be_changed() -> None:
    """persistence 固定为 sqlite，其他值校验失败。"""
    with pytest.raises(ValidationError):
        _response(persistence="persisted")


def test_response_agent_automation_cannot_be_changed() -> None:
    """agent_automation 固定为 disabled，其他值校验失败。"""
    with pytest.raises(ValidationError):
        _response(agent_automation="enabled")


def test_placeholder_tasks_default_empty() -> None:
    """未提供 placeholder_tasks 时默认空列表。"""
    response = CreateGroupChatResponse(
        group_chat=_chat(),
        topic=_topic(),
        members=[_member()],
        initial_messages=[_message()],
        team_run=_team_run(),
        artifact_summary=_artifact_summary(),
        team_status=_team_status(),
        activity_summary=_activity_summary(),
    )
    assert response.placeholder_tasks == []


def test_response_embeds_domain_objects() -> None:
    """响应可内嵌 Project / ResearchQuestion / ResearchState / Task 领域对象。"""
    response = _response()
    assert response.project is not None
    assert response.project.data_space is DataSpace.SYNTHETIC
    assert response.research_question is not None
    assert response.research_state is not None
    assert response.research_state.data_space is DataSpace.SYNTHETIC
    assert len(response.placeholder_tasks) == 1
    assert response.placeholder_tasks[0].status is TaskStatus.PENDING


def test_group_chat_data_space_defaults_synthetic() -> None:
    """group_chat.data_space 默认 synthetic；服务层（Task 10）负责固定输出为 synthetic。"""
    assert _chat().data_space is DataSpace.SYNTHETIC
