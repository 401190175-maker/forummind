"""`app.domain.schemas` 汇总导出测试。

验证稳定入口 `app.domain.schemas` 可以导入七类核心对象
与跨对象共享的枚举和值对象，且导出名称与各对象文件中的
类名保持一致、导出对象与来源模块中的类为同一对象。
"""

import importlib
import inspect

import pytest
from pydantic import BaseModel

import app.domain.schemas as schemas

# 每个导出名称对应的来源模块（导出名称与来源模块中的类名保持一致）。
_EXPORT_SOURCES = {
    # 七类核心对象
    "Project": "app.domain.schemas.project",
    "ResearchQuestion": "app.domain.schemas.research_question",
    "AgentProfile": "app.domain.schemas.agent_profile",
    "Task": "app.domain.schemas.task",
    "Claim": "app.domain.schemas.claim",
    "Evidence": "app.domain.schemas.evidence",
    "ResearchState": "app.domain.schemas.research_state",
    # 共享枚举与值对象（来自 common.py）
    "ObjectId": "app.domain.schemas.common",
    "ObjectType": "app.domain.schemas.common",
    "ObjectReference": "app.domain.schemas.common",
    "VersionInfo": "app.domain.schemas.common",
    "DataSpace": "app.domain.schemas.common",
    "SourceType": "app.domain.schemas.common",
    "VerificationStatus": "app.domain.schemas.common",
    "ObjectLifecycleStatus": "app.domain.schemas.common",
    "AgentRole": "app.domain.schemas.common",
    "TaskStatus": "app.domain.schemas.common",
    "ClaimStatus": "app.domain.schemas.common",
}

# 七类核心对象名（任务完成标准显式列出）。
_CORE_OBJECT_NAMES = (
    "Project",
    "ResearchQuestion",
    "AgentProfile",
    "Task",
    "Claim",
    "Evidence",
    "ResearchState",
)


def test_module_is_importable() -> None:
    """`app.domain.schemas` 可被导入。"""
    module = importlib.import_module("app.domain.schemas")
    assert module.__name__ == "app.domain.schemas"


def test_seven_core_objects_importable_from_entry_point() -> None:
    """可从 `app.domain.schemas` 导入七类核心对象。"""
    from app.domain.schemas import (  # noqa: F401
        AgentProfile,
        Claim,
        Evidence,
        Project,
        ResearchQuestion,
        ResearchState,
        Task,
    )

    for name in _CORE_OBJECT_NAMES:
        assert hasattr(schemas, name)


def test_core_objects_are_pydantic_models() -> None:
    """七类核心对象均为 Pydantic 校验模型。"""
    for name in _CORE_OBJECT_NAMES:
        obj = getattr(schemas, name)
        assert isinstance(obj, type) and issubclass(obj, BaseModel)


@pytest.mark.parametrize("name", sorted(_CORE_OBJECT_NAMES))
def test_core_object_export_matches_source_class(name: str) -> None:
    """核心对象导出与来源模块中的类为同一对象。"""
    source_module = importlib.import_module(_EXPORT_SOURCES[name])
    assert getattr(schemas, name) is getattr(source_module, name)


@pytest.mark.parametrize("name", sorted(_EXPORT_SOURCES))
def test_export_name_matches_source_class_name(name: str) -> None:
    """每个导出名称与来源模块中的类名保持一致，且为同一对象。"""
    assert name in schemas.__all__
    assert hasattr(schemas, name)
    source_module = importlib.import_module(_EXPORT_SOURCES[name])
    assert getattr(schemas, name) is getattr(source_module, name)


def test_all_contains_exactly_required_exports() -> None:
    """`__all__` 恰好覆盖七类核心对象与共享契约，不多不少。"""
    assert set(schemas.__all__) == set(_EXPORT_SOURCES)


def test_public_surface_only_contains_exports() -> None:
    """`app.domain.schemas` 除子模块与 `__all__` 导出外不含其他公共成员。

    包命名空间会附带各 schema 子模块（如 project、common），
    因此只检查非模块公共成员必须全部来自 `__all__`，
    防止在入口文件里混入业务逻辑成员。
    """
    public_non_module_names = {
        name
        for name, value in vars(schemas).items()
        if not name.startswith("__") and not inspect.ismodule(value)
    }
    assert public_non_module_names == set(schemas.__all__)
