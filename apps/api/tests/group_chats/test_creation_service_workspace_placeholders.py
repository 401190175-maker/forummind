"""工作台占位构造测试（Task 11）。

覆盖：`create_group_chat` 输出中的团队运行、产物摘要、成员状态、
课题组动态与课题阶段占位，全部保持“未启动 / 无真实文件 /
成员默认空闲 / 无新动态”语义。
"""

from app.group_chats.creation_service import (
    build_activity_summary,
    build_artifact_summary,
    build_chat_members,
    build_team_run,
    build_team_status,
    create_group_chat,
)
from app.group_chats.schemas import (
    CreateGroupChatRequest,
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)

from app.demo_data.loader import load_demo_package

_PACKAGE = load_demo_package("foam_concrete_case")


def _request() -> CreateGroupChatRequest:
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
    )


def test_team_run_placeholder_not_started() -> None:
    """team_run 占位：status=not_started、automation_enabled=false。"""
    response = create_group_chat(_request())
    assert response.team_run.status == "not_started"
    assert response.team_run.automation_enabled is False
    assert response.team_run.started_at is None


def test_artifact_summary_has_no_real_files() -> None:
    """产物摘要占位：latest_files 为空，不创建真实文件。"""
    response = create_group_chat(_request())
    assert response.artifact_summary.latest_files == []


def test_artifact_summary_folders_per_member_plus_meeting() -> None:
    """产物摘要文件夹：每个成员一个文件夹 + 例会记录文件夹。"""
    members = build_chat_members("gc-001", _request().member_selection, _PACKAGE)
    summary = build_artifact_summary("gc-001", members)
    assert summary.folders == [member.id for member in members] + ["例会记录"]
    assert "例会记录" in summary.folders
    assert len(summary.folders) == len(members) + 1


def test_artifact_summary_naming_rule() -> None:
    """文件命名规则表达“日期 + 任务名 + Agent 名”。"""
    response = create_group_chat(_request())
    rule = response.artifact_summary.naming_rule
    assert "日期" in rule
    assert "任务名" in rule
    assert "Agent 名" in rule


def test_team_status_existing_idle_generate_pending() -> None:
    """成员状态：已有 Agent 默认 idle，生成占位默认 pending_generation。"""
    members = build_chat_members("gc-001", _request().member_selection, _PACKAGE)
    summary = build_team_status("gc-001", members)
    statuses = {
        entry.member_id: entry.status for entry in summary.member_statuses
    }
    assert statuses["gc-001:postdoc:agent-postdoc-1"] == "idle"
    assert statuses["gc-001:phd_student:agent-phd-1"] == "idle"
    assert statuses["gc-001:master_student:gen-1"] == "pending_generation"
    assert statuses["gc-001:master_student:gen-3"] == "pending_generation"


def test_team_status_legend_present() -> None:
    """状态灯图例包含 idle / working / meeting_or_discussing。"""
    run = build_team_run("gc-001")
    members = build_chat_members("gc-001", _request().member_selection, _PACKAGE)
    summary = build_team_status(run.group_chat_id, members)
    assert summary.legend == ["idle", "working", "meeting_or_discussing"]


def test_activity_summary_no_new_activity() -> None:
    """课题组动态占位：无新交付、无新讨论记录、默认课题形成阶段。"""
    response = create_group_chat(_request())
    assert response.activity_summary.new_artifact_count == 0
    assert response.activity_summary.latest_artifact_refs == []
    assert response.activity_summary.has_new_discussion_records is False
    assert response.activity_summary.latest_discussion_refs == []


def test_activity_summary_project_phase_topic_formation() -> None:
    """课题阶段默认 topic_formation。"""
    response = create_group_chat(_request())
    assert response.project_phase.value == "topic_formation"
    assert response.activity_summary.project_phase.value == "topic_formation"
    assert response.group_chat.project_phase.value == "topic_formation"


def test_activity_summary_builder_overview() -> None:
    """课题组动态成员状态概览来自成员状态。"""
    members = build_chat_members("gc-002", _request().member_selection, _PACKAGE)
    summary = build_activity_summary("gc-002", members)
    assert "2 名成员空闲" in summary.member_status_overview
    assert "3 名成员待生成" in summary.member_status_overview
