"""`app.domain.schemas.common` 通用契约测试。"""

import importlib

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.schemas.common import (
    AgentRole,
    ClaimStatus,
    DataSpace,
    ObjectLifecycleStatus,
    ObjectReference,
    ObjectType,
    SourceType,
    TaskStatus,
    VerificationStatus,
    VersionInfo,
)


def test_module_is_importable() -> None:
    """`app.domain.schemas.common` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.common")
    assert module.__name__ == "app.domain.schemas.common"


def test_object_reference_carries_type_id_and_version() -> None:
    """对象引用完整表达对象类型、对象 ID 与版本。"""
    ref = ObjectReference(
        object_type=ObjectType.CLAIM,
        object_id="claim-1",
        version="v2",
    )
    assert ref.object_type is ObjectType.CLAIM
    assert ref.object_id == "claim-1"
    assert ref.version == "v2"


def test_object_reference_without_version_is_current_reference() -> None:
    """对象引用缺省版本时表示“当前”弱引用。"""
    ref = ObjectReference(
        object_type=ObjectType.RESEARCH_QUESTION,
        object_id="rq-1",
    )
    assert ref.version is None


def test_object_reference_missing_type_raises() -> None:
    """对象引用缺少对象类型时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ObjectReference(object_id="claim-1", version="v1")


def test_object_reference_missing_id_raises() -> None:
    """对象引用缺少对象 ID 时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ObjectReference(object_type=ObjectType.CLAIM, version="v1")


def test_object_reference_empty_id_raises() -> None:
    """对象引用不允许空对象 ID。"""
    with pytest.raises(ValidationError):
        ObjectReference(object_type=ObjectType.CLAIM, object_id="")


def test_object_reference_blank_id_raises() -> None:
    """对象引用不允许纯空白对象 ID。"""
    with pytest.raises(ValidationError):
        ObjectReference(object_type=ObjectType.CLAIM, object_id="   ")


def test_object_reference_invalid_type_raises() -> None:
    """对象引用使用未定义对象类型时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ObjectReference(object_type="not-an-object", object_id="claim-1")


def test_data_space_distinguishes_required_spaces() -> None:
    """数据空间至少区分真实、脱敏真实、可核查公开来源、合成。"""
    assert DataSpace.REAL.value == "real"
    assert DataSpace.DESENSITIZED_REAL.value == "desensitized_real"
    assert DataSpace.VERIFIABLE_PUBLIC.value == "verifiable_public"
    assert DataSpace.SYNTHETIC.value == "synthetic"
    assert len(DataSpace) == 4


def test_data_space_accepts_defined_value() -> None:
    """数据空间接受已定义值。"""
    assert TypeAdapter(DataSpace).validate_python("real") is DataSpace.REAL


def test_data_space_invalid_value_raises() -> None:
    """非法数据空间值触发 ValidationError。"""
    with pytest.raises(ValidationError):
        TypeAdapter(DataSpace).validate_python("fake-space")


def test_shared_enum_members_present() -> None:
    """共享枚举包含任务要求的成员。"""
    assert {member.value for member in SourceType} == {
        "literature",
        "experiment",
        "public",
        "user_uploaded",
        "synthetic_demo",
    }
    assert {member.value for member in VerificationStatus} == {
        "lead",
        "pending",
        "verified",
        "rejected",
    }
    assert {member.value for member in ObjectLifecycleStatus} == {
        "draft",
        "active",
        "completed",
        "archived",
        "deleted",
    }
    assert {member.value for member in AgentRole} == {
        "master_student",
        "phd_student",
        "postdoc",
        "group_meeting_secretary",
    }
    assert {member.value for member in TaskStatus} == {
        "pending",
        "in_progress",
        "blocked",
        "completed",
        "cancelled",
    }
    assert {member.value for member in ClaimStatus} == {
        "candidate",
        "supported",
        "weakened",
        "undecidable",
        "withdrawn",
    }


@pytest.mark.parametrize(
    ("enum_cls", "valid_value"),
    [
        (SourceType, "literature"),
        (VerificationStatus, "verified"),
        (ObjectLifecycleStatus, "active"),
        (AgentRole, "postdoc"),
        (TaskStatus, "in_progress"),
        (ClaimStatus, "supported"),
    ],
)
def test_shared_enum_accepts_defined_value(enum_cls: type, valid_value: str) -> None:
    """共享枚举接受已定义值。"""
    assert TypeAdapter(enum_cls).validate_python(valid_value).value == valid_value


@pytest.mark.parametrize(
    "enum_cls",
    [
        SourceType,
        VerificationStatus,
        ObjectLifecycleStatus,
        AgentRole,
        TaskStatus,
        ClaimStatus,
    ],
)
def test_shared_enum_invalid_value_raises(enum_cls: type) -> None:
    """共享枚举的非法值触发 ValidationError。"""
    with pytest.raises(ValidationError):
        TypeAdapter(enum_cls).validate_python("not-a-real-value")


def test_version_info_carries_version_and_previous_reference() -> None:
    """版本元信息表达版本号与上一版本引用。"""
    info = VersionInfo(
        version="v2",
        previous_version_id=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id="rq-1",
            version="v1",
        ),
    )
    assert info.version == "v2"
    assert info.previous_version_id is not None
    assert info.previous_version_id.object_id == "rq-1"
    assert info.previous_version_id.version == "v1"


def test_version_info_previous_reference_optional() -> None:
    """版本元信息允许缺省上一版本引用（首个版本）。"""
    info = VersionInfo(version="v1")
    assert info.previous_version_id is None
