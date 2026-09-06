"""`app.domain.schemas.task` 科研工作单元对象契约测试。"""

import importlib
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.domain.schemas.common import ObjectReference, ObjectType, TaskStatus
from app.domain.schemas.task import Task


def test_module_is_importable() -> None:
    """`app.domain.schemas.task` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.task")
    assert module.__name__ == "app.domain.schemas.task"


def test_task_minimal_construction() -> None:
    """Task 可只凭标题、所属 Project、期望输出对象类型与任务状态构造最小合法对象。"""
    task = Task(
        title="整理泡沫混凝土抗压强度数据",
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        expected_output_object_type=ObjectType.EVIDENCE,
        status=TaskStatus.PENDING,
    )
    assert task.title == "整理泡沫混凝土抗压强度数据"
    assert task.project is not None
    assert task.project.object_type is ObjectType.PROJECT
    assert task.project.object_id == "proj-2026-001"
    assert task.expected_output_object_type is ObjectType.EVIDENCE
    assert task.status is TaskStatus.PENDING
    assert task.description is None
    assert task.assigner is None
    assert task.assignee is None
    assert task.input_versions == []
    assert task.deadline is None
    assert task.priority is None


def test_task_expresses_full_semantics() -> None:
    """Task 完整表达标题、说明、Project、指派者/执行者、输入版本、期望输出类型、状态、截止时间与优先级。"""
    task = Task(
        title="验证泡沫混凝土抗压强度机理假设",
        description="汇总实验数据并给出可验证预测",
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        assigner=ObjectReference(object_type=ObjectType.AGENT_PROFILE, object_id="agent-phd-1"),
        assignee=ObjectReference(object_type=ObjectType.AGENT_PROFILE, object_id="agent-ms-1"),
        input_versions=[
            ObjectReference(
                object_type=ObjectType.RESEARCH_QUESTION,
                object_id="rq-2026-001",
                version="v2",
            ),
            ObjectReference(
                object_type=ObjectType.CLAIM,
                object_id="claim-2026-001",
                version="v1",
            ),
        ],
        expected_output_object_type=ObjectType.CLAIM,
        status=TaskStatus.IN_PROGRESS,
        deadline=datetime(2026, 6, 30),
        priority="高",
    )
    assert task.title == "验证泡沫混凝土抗压强度机理假设"
    assert task.description == "汇总实验数据并给出可验证预测"
    assert task.project is not None
    assert task.project.object_type is ObjectType.PROJECT
    assert task.project.object_id == "proj-2026-001"
    assert task.assigner is not None
    assert task.assigner.object_type is ObjectType.AGENT_PROFILE
    assert task.assigner.object_id == "agent-phd-1"
    assert task.assignee is not None
    assert task.assignee.object_type is ObjectType.AGENT_PROFILE
    assert task.assignee.object_id == "agent-ms-1"
    assert [ref.object_id for ref in task.input_versions] == ["rq-2026-001", "claim-2026-001"]
    assert task.input_versions[0].version == "v2"
    assert task.input_versions[1].version == "v1"
    assert task.expected_output_object_type is ObjectType.CLAIM
    assert task.status is TaskStatus.IN_PROGRESS
    assert task.deadline == datetime(2026, 6, 30)
    assert task.priority == "高"


def test_task_missing_status_raises() -> None:
    """Task 未定义任务状态时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Task(
            title="整理泡沫混凝土抗压强度数据",
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            expected_output_object_type=ObjectType.EVIDENCE,
        )


def test_task_missing_project_raises() -> None:
    """Task 缺少所属 Project 时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Task(
            title="整理泡沫混凝土抗压强度数据",
            expected_output_object_type=ObjectType.EVIDENCE,
            status=TaskStatus.PENDING,
        )


def test_task_missing_title_raises() -> None:
    """Task 缺少任务标题时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Task(
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            expected_output_object_type=ObjectType.EVIDENCE,
            status=TaskStatus.PENDING,
        )


def test_task_missing_expected_output_type_raises() -> None:
    """Task 缺少期望输出对象类型时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Task(
            title="整理泡沫混凝土抗压强度数据",
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            status=TaskStatus.PENDING,
        )


@pytest.mark.parametrize("title", ["", "   "])
def test_task_blank_title_raises(title: str) -> None:
    """Task 标题不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        Task(
            title=title,
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            expected_output_object_type=ObjectType.EVIDENCE,
            status=TaskStatus.PENDING,
        )


@pytest.mark.parametrize("status", ["fake-status", "not-a-status"])
def test_task_invalid_status_raises(status: str) -> None:
    """Task 任务状态使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Task(
            title="整理泡沫混凝土抗压强度数据",
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            expected_output_object_type=ObjectType.EVIDENCE,
            status=status,
        )


def test_task_status_accepts_defined_value() -> None:
    """Task 任务状态接受已定义枚举值。"""
    task = Task(
        title="整理泡沫混凝土抗压强度数据",
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        expected_output_object_type=ObjectType.EVIDENCE,
        status="in_progress",
    )
    assert task.status is TaskStatus.IN_PROGRESS


@pytest.mark.parametrize("output_type", ["fake-type", "not-an-object"])
def test_task_invalid_expected_output_type_raises(output_type: str) -> None:
    """Task 期望输出对象类型使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Task(
            title="整理泡沫混凝土抗压强度数据",
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            expected_output_object_type=output_type,
            status=TaskStatus.PENDING,
        )


def test_task_field_surface_avoids_forbidden_dimensions() -> None:
    """Task 只包含契约字段，不包含队列任务、异步调度、Agent 自动执行记录或 Memory 写入字段。"""
    assert set(Task.model_fields) == {
        "title",
        "description",
        "project",
        "assigner",
        "assignee",
        "input_versions",
        "expected_output_object_type",
        "status",
        "deadline",
        "priority",
    }
