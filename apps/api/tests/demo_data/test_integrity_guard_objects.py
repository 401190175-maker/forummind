"""`app.demo_data.integrity_guard` 派生对象级完整性保护测试。

以 `reset_demo_objects` 的真实输出为合法基线，各负向用例通过
深拷贝后篡改派生对象标签，验证 guard 拒绝。
"""

import importlib

import pytest

from app.demo_data.integrity_guard import (
    DemoIntegrityError,
    validate_demo_object_integrity,
)
from app.demo_data.object_factory import reset_demo_objects
from app.domain.schemas import DataSpace, SourceType, VerificationStatus


def test_module_is_importable() -> None:
    """`app.demo_data.integrity_guard` 可被导入。"""
    module = importlib.import_module("app.demo_data.integrity_guard")
    assert module.__name__ == "app.demo_data.integrity_guard"


def _fresh_bundle():
    """reset 真实数据包并返回深拷贝，避免用例间互相污染。"""
    return reset_demo_objects("foam_concrete_case").model_copy(deep=True)


def test_valid_bundle_passes_object_integrity_guard() -> None:
    """合法 DemoObjectBundle 通过 integrity guard。"""
    validate_demo_object_integrity(_fresh_bundle())


def test_non_synthetic_project_rejected() -> None:
    """Project 不是 DataSpace.SYNTHETIC 时拒绝。"""
    bundle = _fresh_bundle()
    bundle.project.data_space = DataSpace.REAL
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_object_integrity(bundle)
    assert "Project" in str(excinfo.value)
    assert "SYNTHETIC" in str(excinfo.value)


def test_non_synthetic_research_state_rejected() -> None:
    """ResearchState 不是 DataSpace.SYNTHETIC 时拒绝。"""
    bundle = _fresh_bundle()
    bundle.research_state.data_space = DataSpace.REAL
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_object_integrity(bundle)
    assert "ResearchState" in str(excinfo.value)


def test_evidence_losing_synthetic_space_rejected() -> None:
    """任一 demo Evidence 丢失 DataSpace.SYNTHETIC 时拒绝。"""
    bundle = _fresh_bundle()
    bundle.evidence[0].data_space = DataSpace.REAL
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_object_integrity(bundle)
    assert "Evidence" in str(excinfo.value)
    assert "data_space" in str(excinfo.value)


def test_evidence_with_wrong_source_type_rejected() -> None:
    """任一 demo Evidence 不是 SourceType.SYNTHETIC_DEMO 时拒绝。"""
    bundle = _fresh_bundle()
    bundle.evidence[0].source_type = SourceType.LITERATURE
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_object_integrity(bundle)
    assert "source_type" in str(excinfo.value)


def test_verified_literature_lead_rejected() -> None:
    """文献线索 Evidence 被标记为 VerificationStatus.VERIFIED 时拒绝。"""
    bundle = _fresh_bundle()
    lead_evidence = bundle.evidence[0]
    assert "literature_leads" in lead_evidence.source_location
    lead_evidence.verification_status = VerificationStatus.VERIFIED
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_object_integrity(bundle)
    assert "VERIFIED" in str(excinfo.value)
