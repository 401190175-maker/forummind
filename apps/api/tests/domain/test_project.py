"""`app.domain.schemas.project` 课题空间对象契约测试。"""

import importlib

import pytest
from pydantic import ValidationError

from app.domain.schemas.common import (
    DataSpace,
    ObjectLifecycleStatus,
    ObjectReference,
    ObjectType,
)
from app.domain.schemas.project import Project, ProjectConstraints


def test_module_is_importable() -> None:
    """`app.domain.schemas.project` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.project")
    assert module.__name__ == "app.domain.schemas.project"


def test_project_minimal_construction() -> None:
    """Project 可只凭标题、数据空间与课题状态构造最小合法对象。"""
    project = Project(
        title="废弃泥浆基泡沫混凝土机理-性能-制备研究",
        data_space=DataSpace.REAL,
        status=ObjectLifecycleStatus.DRAFT,
    )
    assert project.title == "废弃泥浆基泡沫混凝土机理-性能-制备研究"
    assert project.data_space is DataSpace.REAL
    assert project.status is ObjectLifecycleStatus.DRAFT
    assert project.description is None
    assert project.current_research_question is None
    assert project.current_research_state is None
    assert project.agent_profiles == []
    assert project.constraints is None


def test_project_expresses_full_semantics() -> None:
    """Project 完整表达标题、描述、数据空间、状态、对象引用与约束摘要。"""
    project = Project(
        title="废弃泥浆基泡沫混凝土机理研究",
        description="围绕废弃泥浆基泡沫混凝土的机理、性能与制备开展全链条研究",
        data_space=DataSpace.DESENSITIZED_REAL,
        status=ObjectLifecycleStatus.ACTIVE,
        current_research_question=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id="rq-2026-001",
        ),
        current_research_state=ObjectReference(
            object_type=ObjectType.RESEARCH_STATE,
            object_id="rs-2026-001",
        ),
        agent_profiles=[
            ObjectReference(object_type=ObjectType.AGENT_PROFILE, object_id="agent-ms-1"),
            ObjectReference(object_type=ObjectType.AGENT_PROFILE, object_id="agent-phd-1"),
        ],
        constraints=ProjectConstraints(
            timeline="6 个月",
            cost="预算 10 万元",
            equipment="SEM、XRD、万能试验机",
            materials_scope="废弃泥浆、水泥、发泡剂",
        ),
    )
    assert project.title == "废弃泥浆基泡沫混凝土机理研究"
    assert project.description == "围绕废弃泥浆基泡沫混凝土的机理、性能与制备开展全链条研究"
    assert project.data_space is DataSpace.DESENSITIZED_REAL
    assert project.status is ObjectLifecycleStatus.ACTIVE
    assert project.current_research_question is not None
    assert project.current_research_question.object_type is ObjectType.RESEARCH_QUESTION
    assert project.current_research_question.object_id == "rq-2026-001"
    assert project.current_research_question.version is None
    assert project.current_research_state is not None
    assert project.current_research_state.object_type is ObjectType.RESEARCH_STATE
    assert project.current_research_state.object_id == "rs-2026-001"
    assert [ref.object_id for ref in project.agent_profiles] == ["agent-ms-1", "agent-phd-1"]
    assert project.constraints is not None
    assert project.constraints.timeline == "6 个月"
    assert project.constraints.cost == "预算 10 万元"
    assert project.constraints.equipment == "SEM、XRD、万能试验机"
    assert project.constraints.materials_scope == "废弃泥浆、水泥、发泡剂"


def test_project_missing_title_raises() -> None:
    """Project 缺少标题时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Project(data_space=DataSpace.REAL, status=ObjectLifecycleStatus.DRAFT)


def test_project_missing_data_space_raises() -> None:
    """Project 缺少数据空间时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Project(title="废弃泥浆基泡沫混凝土机理研究", status=ObjectLifecycleStatus.DRAFT)


def test_project_missing_status_raises() -> None:
    """Project 缺少课题状态时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Project(title="废弃泥浆基泡沫混凝土机理研究", data_space=DataSpace.REAL)


@pytest.mark.parametrize("title", ["", "   "])
def test_project_blank_title_raises(title: str) -> None:
    """Project 标题不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        Project(
            title=title,
            data_space=DataSpace.REAL,
            status=ObjectLifecycleStatus.DRAFT,
        )


@pytest.mark.parametrize("data_space", ["fake-space", "not-a-space"])
def test_project_invalid_data_space_raises(data_space: str) -> None:
    """Project 数据空间使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Project(
            title="废弃泥浆基泡沫混凝土机理研究",
            data_space=data_space,
            status=ObjectLifecycleStatus.DRAFT,
        )


@pytest.mark.parametrize("status", ["fake-status", "not-a-status"])
def test_project_invalid_status_raises(status: str) -> None:
    """Project 课题状态使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Project(
            title="废弃泥浆基泡沫混凝土机理研究",
            data_space=DataSpace.REAL,
            status=status,
        )


def test_project_field_surface_avoids_forbidden_dimensions() -> None:
    """Project 只包含契约字段，不包含租户隔离、文件权限执行或 Memory 时间线字段。"""
    assert set(Project.model_fields) == {
        "title",
        "description",
        "data_space",
        "status",
        "current_research_question",
        "current_research_state",
        "agent_profiles",
        "constraints",
    }
