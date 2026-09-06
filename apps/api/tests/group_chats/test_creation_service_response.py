"""核心创建服务测试（Task 10）。

覆盖：`create_group_chat` 返回完整响应（group_chat / topic / members /
initial_messages / 关联 synthetic 科研对象 / 任务占位开关），
    固定边界声明（sqlite / disabled / synthetic），
初始系统消息包含课题名称与概述。
"""

from app.domain.schemas import DataSpace, TaskStatus
from app.group_chats import creation_service as creation_service_module
from app.group_chats.creation_service import create_group_chat
from app.group_chats.schemas import (
    CreateGroupChatRequest,
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)
from app.storage.sqlite_store import SQLiteStore


def _request(
    create_placeholder_tasks: bool = True,
    demo_package_id: str = "foam_concrete_case",
) -> CreateGroupChatRequest:
    return CreateGroupChatRequest(
        topic_name="废弃泥浆基泡沫混凝土",
        topic_summary="研究废弃泥浆基泡沫混凝土的机理与性能",
        member_selection=MemberSelection(
            postdoc=RoleMemberSelection(
                selection_mode=SelectionMode.EXISTING,
                agent_ids=["agent-postdoc-1"],
            ),
            phd_student=RoleMemberSelection(
                selection_mode=SelectionMode.EXISTING,
                agent_ids=["agent-phd-1"],
            ),
            master_student=RoleMemberSelection(
                selection_mode=SelectionMode.GENERATE,
                count=3,
            ),
        ),
        demo_package_id=demo_package_id,
        data_space=DataSpace.SYNTHETIC,
        create_placeholder_tasks=create_placeholder_tasks,
    )


def test_create_group_chat_returns_full_response() -> None:
    """成功创建返回完整响应：group_chat、topic、members、initial_messages。"""
    response = create_group_chat(_request())
    assert response.group_chat.id.startswith("gc-")
    assert response.group_chat.topic_name == "废弃泥浆基泡沫混凝土"
    assert response.topic.topic_name == "废弃泥浆基泡沫混凝土"
    assert response.topic.topic_summary == "研究废弃泥浆基泡沫混凝土的机理与性能"
    assert len(response.members) == 5
    assert len(response.initial_messages) >= 1


def test_create_group_chat_returns_synthetic_research_objects() -> None:
    """响应关联 synthetic Project / ResearchQuestion / ResearchState。"""
    response = create_group_chat(_request())
    assert response.project is not None
    assert response.project.data_space is DataSpace.SYNTHETIC
    assert response.research_question is not None
    assert response.research_state is not None
    assert response.research_state.data_space is DataSpace.SYNTHETIC


def test_topic_refs_point_to_research_objects() -> None:
    """topic 的科研对象引用指向确定性对象 ID。"""
    response = create_group_chat(_request())
    assert response.topic.project_ref is not None
    assert response.topic.project_ref.object_id == (
        "foam_concrete_case@0.1.0:project:project"
    )
    assert response.topic.research_question_ref is not None
    assert response.topic.research_question_ref.object_id == (
        "foam_concrete_case@0.1.0:research_question:research_question"
    )
    assert response.topic.research_state_ref is not None
    assert response.topic.research_state_ref.object_id == (
        "foam_concrete_case@0.1.0:research_state:research_state"
    )


def test_placeholder_tasks_returned_when_enabled() -> None:
    """create_placeholder_tasks=true 时返回待分配任务占位（全部 PENDING）。"""
    response = create_group_chat(_request(create_placeholder_tasks=True))
    assert len(response.placeholder_tasks) >= 1
    assert all(
        task.status is TaskStatus.PENDING
        for task in response.placeholder_tasks
    )


def test_placeholder_tasks_empty_when_disabled() -> None:
    """create_placeholder_tasks=false 时 placeholder_tasks 为空列表。"""
    response = create_group_chat(_request(create_placeholder_tasks=False))
    assert response.placeholder_tasks == []


def test_initial_messages_include_topic_name_and_summary() -> None:
    """初始系统消息内容包含课题名称和课题概述。"""
    response = create_group_chat(_request())
    contents = " ".join(message.content for message in response.initial_messages)
    assert "废弃泥浆基泡沫混凝土" in contents
    assert "研究废弃泥浆基泡沫混凝土的机理与性能" in contents


def test_response_fixed_boundary_declarations() -> None:
    """响应明确 synthetic / sqlite / disabled。"""
    response = create_group_chat(_request())
    assert response.persistence == "sqlite"
    assert response.agent_automation == "disabled"
    assert response.group_chat.data_space is DataSpace.SYNTHETIC
    assert response.warnings


def test_members_consistent_with_group_chat_id() -> None:
    """所有成员与占位对象的 group_chat_id 与 group_chat.id 一致。"""
    response = create_group_chat(_request())
    group_chat_id = response.group_chat.id
    assert all(member.group_chat_id == group_chat_id for member in response.members)
    assert response.team_run.group_chat_id == group_chat_id
    assert response.artifact_summary.group_chat_id == group_chat_id
    assert response.team_status.group_chat_id == group_chat_id
    assert response.activity_summary.group_chat_id == group_chat_id


def test_service_does_not_persist_or_run_agents() -> None:
    """服务输出不包含持久化/Agent 执行痕迹：任务全部 PENDING、team_run 未启动。"""
    response = create_group_chat(_request())
    assert response.team_run.status == "not_started"
    assert response.team_run.automation_enabled is False
    assert all(task.status is TaskStatus.PENDING for task in response.placeholder_tasks)


def test_group_chat_is_recovered_after_process_cache_clear(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    previous_store = creation_service_module._persistence_store
    creation_service_module.configure_persistence(store)
    try:
        response = create_group_chat(_request())
        creation_service_module._created_group_chats.clear()

        recovered = creation_service_module.get_created_group_chat(
            response.group_chat.id
        )

        assert recovered is not None
        assert recovered.topic.topic_name == response.topic.topic_name
        assert [member.id for member in recovered.members] == [
            member.id for member in response.members
        ]
    finally:
        creation_service_module.reset_created_group_chats()
        creation_service_module.configure_persistence(previous_store)
        store.close()
