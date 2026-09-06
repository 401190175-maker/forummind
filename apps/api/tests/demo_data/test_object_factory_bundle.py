"""`app.demo_data.object_factory` ResearchState 与 DemoObjectBundle 测试。

覆盖：初始 synthetic ResearchState 构造、完整对象集合汇总、
`reset_demo_objects` 的确定性语义（两次 reset 结果一致）。
"""

import importlib

from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import (
    DemoObjectBundle,
    build_demo_objects,
    build_research_state,
    evidence_ref,
    make_object_id,
    reset_demo_objects,
)
from app.domain.schemas import DataSpace, ObjectType, ResearchState


def test_module_is_importable() -> None:
    """`app.demo_data.object_factory` 可被导入。"""
    module = importlib.import_module("app.demo_data.object_factory")
    assert module.__name__ == "app.demo_data.object_factory"


def test_build_research_state_is_synthetic_and_typed() -> None:
    """初始 ResearchState 的 data_space 必须是 SYNTHETIC。"""
    package = load_demo_package("foam_concrete_case")
    state = build_research_state(package)
    assert isinstance(state, ResearchState)
    assert state.data_space is DataSpace.SYNTHETIC


def test_research_state_version_tracks_package_version() -> None:
    """ResearchState 快照版本取数据包版本，保持确定性。"""
    package = load_demo_package("foam_concrete_case")
    state = build_research_state(package)
    assert state.version.version == package.version


def test_research_state_references_initial_question_and_evidence() -> None:
    """ResearchState 引用初始 ResearchQuestion 与关键 Evidence。"""
    package = load_demo_package("foam_concrete_case")
    state = build_research_state(package)
    assert state.current_research_question.object_type is ObjectType.RESEARCH_QUESTION
    assert state.current_research_question.object_id == make_object_id(
        package, ObjectType.RESEARCH_QUESTION, "research_question"
    )
    expected_keys = package.expected_initial_state.key_evidence_local_keys
    assert [ref.object_id for ref in state.key_evidence] == [
        evidence_ref(package, key).object_id for key in expected_keys
    ]
    assert state.evidence_gaps_summary == (
        package.expected_initial_state.evidence_gaps_summary
    )
    assert state.unresolved_disagreements_summary == (
        package.expected_initial_state.unresolved_disagreements_summary
    )


def test_build_demo_objects_returns_complete_bundle() -> None:
    """DemoObjectBundle 包含 Project、ResearchQuestion、AgentProfile、Task、Evidence、ResearchState。"""
    package = load_demo_package("foam_concrete_case")
    bundle = build_demo_objects(package)
    assert isinstance(bundle, DemoObjectBundle)
    assert bundle.package_id == package.package_id
    assert bundle.package_version == package.version
    assert bundle.project.data_space is DataSpace.SYNTHETIC
    assert bundle.research_question.phenomenon_or_objective == (
        package.research_direction.phenomenon_or_objective
    )
    assert len(bundle.agent_profiles) == len(package.agent_profiles)
    assert len(bundle.tasks) == len(package.initial_tasks)
    assert len(bundle.evidence) == len(package.literature_leads) + 1
    assert bundle.research_state.data_space is DataSpace.SYNTHETIC


def test_reset_demo_objects_returns_bundle() -> None:
    """`reset_demo_objects("foam_concrete_case")` 返回完整 DemoObjectBundle。"""
    bundle = reset_demo_objects("foam_concrete_case")
    assert isinstance(bundle, DemoObjectBundle)
    assert bundle.package_id == "foam_concrete_case"


def test_reset_is_deterministic_across_two_calls() -> None:
    """两次 reset 得到的对象集合、引用与序列化结果稳定一致。"""
    first = reset_demo_objects("foam_concrete_case")
    second = reset_demo_objects("foam_concrete_case")
    assert first.model_dump() == second.model_dump()
    assert first.model_dump_json() == second.model_dump_json()
    assert first.project.current_research_question == (
        second.project.current_research_question
    )
    assert first.research_state.key_evidence == second.research_state.key_evidence
    assert [task.assignee for task in first.tasks] == [
        task.assignee for task in second.tasks
    ]
