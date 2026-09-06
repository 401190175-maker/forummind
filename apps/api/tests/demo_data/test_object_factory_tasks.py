"""`app.demo_data.object_factory` 初始 Task 构造测试。

覆盖：数据包初始任务到 `Task` 的映射、synthetic Project 关联、
确定性 AgentProfile/Evidence 引用与初始待执行状态。
"""

import importlib

from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import build_initial_tasks, evidence_ref
from app.domain.schemas import ObjectReference, ObjectType, Task, TaskStatus


def test_module_is_importable() -> None:
    """`app.demo_data.object_factory` 可被导入。"""
    module = importlib.import_module("app.demo_data.object_factory")
    assert module.__name__ == "app.demo_data.object_factory"


def test_build_initial_tasks_maps_each_package_task() -> None:
    """数据包内每个初始任务都映射为一个 Task，数量一致。"""
    package = load_demo_package("foam_concrete_case")
    tasks = build_initial_tasks(package)
    assert len(tasks) == len(package.initial_tasks)
    assert all(isinstance(task, Task) for task in tasks)
    assert [task.title for task in tasks] == [spec.title for spec in package.initial_tasks]


def test_task_links_synthetic_project() -> None:
    """每个 Task 通过确定性 ObjectReference 关联 synthetic Project。"""
    package = load_demo_package("foam_concrete_case")
    tasks = build_initial_tasks(package)
    for task in tasks:
        assert isinstance(task.project, ObjectReference)
        assert task.project.object_type is ObjectType.PROJECT
        assert task.project.object_id.startswith("foam_concrete_case@0.1.0:project:")


def test_task_expected_output_uses_object_type_enum() -> None:
    """每个 Task 的 expected_output_object_type 使用现有 ObjectType 枚举且与数据包一致。"""
    package = load_demo_package("foam_concrete_case")
    tasks = build_initial_tasks(package)
    for task, spec in zip(tasks, package.initial_tasks):
        assert isinstance(task.expected_output_object_type, ObjectType)
        assert task.expected_output_object_type.value == spec.expected_output_object_type


def test_task_status_is_pending() -> None:
    """初始 Task 状态为待执行 TaskStatus.PENDING。"""
    package = load_demo_package("foam_concrete_case")
    tasks = build_initial_tasks(package)
    assert len(tasks) > 0
    for task in tasks:
        assert task.status is TaskStatus.PENDING


def test_task_assigner_assignee_use_deterministic_agent_refs() -> None:
    """指派者与执行者使用确定性 AgentProfile 引用，与数据包 local_key 对应。"""
    package = load_demo_package("foam_concrete_case")
    tasks = build_initial_tasks(package)
    for task, spec in zip(tasks, package.initial_tasks):
        assert isinstance(task.assigner, ObjectReference)
        assert task.assigner.object_type is ObjectType.AGENT_PROFILE
        assert task.assigner.object_id.endswith(f":agent_profile:{spec.assigner}")
        assert isinstance(task.assignee, ObjectReference)
        assert task.assignee.object_type is ObjectType.AGENT_PROFILE
        assert task.assignee.object_id.endswith(f":agent_profile:{spec.assignee}")


def test_task_input_versions_use_deterministic_evidence_refs() -> None:
    """输入对象引用指向后续构造的 demo Evidence，且确定性稳定。"""
    package = load_demo_package("foam_concrete_case")
    tasks = build_initial_tasks(package)
    for task, spec in zip(tasks, package.initial_tasks):
        assert len(task.input_versions) == len(spec.input_local_keys)
        for ref, local_key in zip(task.input_versions, spec.input_local_keys):
            assert ref == evidence_ref(package, local_key)
            assert ref.object_type is ObjectType.EVIDENCE


def test_tasks_stable_across_repeated_construction() -> None:
    """同一数据包版本重复构造时 Task 列表与引用稳定不变。"""
    package = load_demo_package("foam_concrete_case")
    first = [task.model_dump() for task in build_initial_tasks(package)]
    second = [task.model_dump() for task in build_initial_tasks(package)]
    assert first == second
