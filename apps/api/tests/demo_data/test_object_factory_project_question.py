"""`app.demo_data.object_factory` Project 与 ResearchQuestion 构造测试。

覆盖：研究方向到 synthetic Project / 初始 ResearchQuestion 的映射、
确定性对象引用、以及同一数据包版本重复构造的稳定性。
"""

import importlib

from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import (
    build_project,
    build_research_question,
    make_object_id,
)
from app.domain.schemas import (
    DataSpace,
    ObjectLifecycleStatus,
    ObjectReference,
    ObjectType,
    Project,
    ResearchQuestion,
)
from app.domain.schemas.project import ProjectConstraints


def test_module_is_importable() -> None:
    """`app.demo_data.object_factory` 可被导入。"""
    module = importlib.import_module("app.demo_data.object_factory")
    assert module.__name__ == "app.demo_data.object_factory"


def test_build_project_returns_synthetic_project() -> None:
    """研究方向映射为 synthetic Project：标题、描述、约束来自数据包。"""
    package = load_demo_package("foam_concrete_case")
    project = build_project(package)
    assert isinstance(project, Project)
    assert project.data_space is DataSpace.SYNTHETIC
    assert project.status is ObjectLifecycleStatus.ACTIVE
    assert project.title == package.research_direction.title
    assert project.description == package.research_direction.description
    assert isinstance(project.constraints, ProjectConstraints)
    assert project.constraints.timeline == package.experiment_constraints.timeline
    assert project.constraints.cost == package.experiment_constraints.cost
    assert project.constraints.equipment == package.experiment_constraints.equipment
    assert (
        project.constraints.materials_scope
        == package.research_direction.material_system
    )


def test_build_project_links_current_research_question_ref() -> None:
    """Project 通过确定性引用指向初始 ResearchQuestion。"""
    package = load_demo_package("foam_concrete_case")
    project = build_project(package)
    ref = project.current_research_question
    assert ref is not None
    assert ref.object_type is ObjectType.RESEARCH_QUESTION
    assert ref.object_id == make_object_id(
        package, ObjectType.RESEARCH_QUESTION, "research_question"
    )


def test_build_research_question_expresses_demo_semantics() -> None:
    """ResearchQuestion 表达材料体系、现象或目标、待解释事项与约束。"""
    package = load_demo_package("foam_concrete_case")
    question = build_research_question(package)
    assert isinstance(question, ResearchQuestion)
    assert (
        question.phenomenon_or_objective
        == package.research_direction.phenomenon_or_objective
    )
    assert question.material_system == package.research_direction.material_system
    assert question.to_explain == package.research_direction.to_explain
    assert "设备：" in question.conditions
    assert "成本：" in question.constraints


def test_research_question_links_synthetic_project() -> None:
    """ResearchQuestion 通过 ObjectReference 关联 synthetic Project。"""
    package = load_demo_package("foam_concrete_case")
    question = build_research_question(package)
    assert isinstance(question.project, ObjectReference)
    assert question.project.object_type is ObjectType.PROJECT
    assert question.project.object_id == make_object_id(
        package, ObjectType.PROJECT, "project"
    )


def test_object_ids_stable_across_repeated_construction() -> None:
    """同一数据包版本重复构造时对象 ID 与引用稳定不变。"""
    package = load_demo_package("foam_concrete_case")
    first = (
        build_project(package).model_dump(),
        build_research_question(package).model_dump(),
    )
    second = (
        build_project(package).model_dump(),
        build_research_question(package).model_dump(),
    )
    assert first == second


def test_object_id_embeds_package_identity() -> None:
    """对象 ID 由 package_id、version、object_type 与 local_key 推导（设计 §4.3）。"""
    package = load_demo_package("foam_concrete_case")
    object_id = make_object_id(package, ObjectType.EVIDENCE, "lit-1")
    assert object_id.startswith("foam_concrete_case@0.1.0:evidence:lit-1")


def test_no_other_object_types_constructed_yet() -> None:
    """本任务阶段不构造 Task、Evidence、AgentProfile、ResearchState（后续任务补充）。"""
    package = load_demo_package("foam_concrete_case")
    project = build_project(package)
    question = build_research_question(package)
    assert project.agent_profiles == []
    assert question.version is None
