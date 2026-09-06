"""工作台占位响应 DTO 测试（Task 6）。

覆盖：`ProjectPhase` 枚举、`TeamRun`、`TeamArtifactSummary`、
`TeamStatusSummary`、`ProjectGroupActivitySummary` 的默认占位语义
（未启动、无真实文件、成员默认空闲、无新动态）。
"""

import pytest
from pydantic import ValidationError

from app.group_chats.schemas import (
    MemberStatusEntry,
    ProjectGroupActivitySummary,
    ProjectPhase,
    TeamArtifactSummary,
    TeamRun,
    TeamStatusSummary,
)


def test_project_phase_values() -> None:
    """ProjectPhase 包含四个课题阶段值。"""
    assert {phase.value for phase in ProjectPhase} == {
        "topic_formation",
        "experiment_design",
        "result_analysis",
        "output_production",
    }


def test_team_run_defaults_not_started() -> None:
    """TeamRun 默认 status=not_started、automation_enabled=false、started_at 为空。"""
    run = TeamRun(id="gc-001:team-run", group_chat_id="gc-001")
    assert run.status == "not_started"
    assert run.automation_enabled is False
    assert run.started_at is None


def test_team_run_automation_cannot_be_enabled() -> None:
    """automation_enabled 固定为 false，不能表达已启用自动化。"""
    with pytest.raises(ValidationError):
        TeamRun(
            id="gc-001:team-run",
            group_chat_id="gc-001",
            automation_enabled=True,
        )


def test_team_artifact_summary_defaults_empty_files() -> None:
    """TeamArtifactSummary 默认无真实文件，latest_files 为空。"""
    summary = TeamArtifactSummary(
        group_chat_id="gc-001",
        folders=["agent-postdoc-1", "agent-phd-1", "例会记录"],
        naming_rule="日期 + 任务名 + Agent 名",
    )
    assert summary.folders == ["agent-postdoc-1", "agent-phd-1", "例会记录"]
    assert summary.latest_files == []
    assert "日期" in summary.naming_rule and "任务名" in summary.naming_rule


def test_team_status_summary_legend_and_entries() -> None:
    """TeamStatusSummary 图例含 idle/working/meeting_or_discussing，成员状态可表达待生成。"""
    summary = TeamStatusSummary(
        group_chat_id="gc-001",
        member_statuses=[
            MemberStatusEntry(
                member_id="gc-001:postdoc:agent-postdoc-1",
                display_name="演示博士后 Agent",
                status="idle",
            ),
            MemberStatusEntry(
                member_id="gc-001:master_student:gen-1",
                display_name="待生成硕士生 Agent 1",
                status="pending_generation",
            ),
        ],
    )
    assert summary.legend == ["idle", "working", "meeting_or_discussing"]
    assert summary.member_statuses[0].status == "idle"
    assert summary.member_statuses[1].status == "pending_generation"


def test_activity_summary_defaults_no_new_activity() -> None:
    """ProjectGroupActivitySummary 默认无新交付、无新讨论、课题形成阶段。"""
    summary = ProjectGroupActivitySummary(
        group_chat_id="gc-001",
        member_status_overview="成员全部空闲",
    )
    assert summary.new_artifact_count == 0
    assert summary.latest_artifact_refs == []
    assert summary.has_new_discussion_records is False
    assert summary.latest_discussion_refs == []
    assert summary.project_phase is ProjectPhase.TOPIC_FORMATION
