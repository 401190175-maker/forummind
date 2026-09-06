"""`app.demo_data.object_factory` Evidence 构造测试。

覆盖：文献线索与初始异常到 synthetic Evidence 的映射、合成标记、
核查状态约束与确定性引用。
"""

import importlib

from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import build_evidence, evidence_ref
from app.domain.schemas import (
    DataSpace,
    Evidence,
    SourceType,
    VerificationStatus,
)
from app.domain.schemas.evidence import DataCategory


def test_module_is_importable() -> None:
    """`app.demo_data.object_factory` 可被导入。"""
    module = importlib.import_module("app.demo_data.object_factory")
    assert module.__name__ == "app.demo_data.object_factory"


def test_build_evidence_returns_leads_plus_anomaly() -> None:
    """Evidence 列表 = 文献线索数 + 1 个初始异常。"""
    package = load_demo_package("foam_concrete_case")
    evidence = build_evidence(package)
    assert len(evidence) == len(package.literature_leads) + 1
    assert all(isinstance(item, Evidence) for item in evidence)


def test_all_evidence_keep_synthetic_markers() -> None:
    """所有 demo Evidence 的 source_type 为 SYNTHETIC_DEMO、data_space 为 SYNTHETIC。"""
    package = load_demo_package("foam_concrete_case")
    evidence = build_evidence(package)
    assert len(evidence) > 0
    for item in evidence:
        assert item.source_type is SourceType.SYNTHETIC_DEMO
        assert item.data_space is DataSpace.SYNTHETIC
        assert item.data_category is DataCategory.TEXT


def test_literature_lead_status_restricted_to_lead_or_pending() -> None:
    """文献线索 Evidence 的核查状态与数据包一致，且只能是 LEAD 或 PENDING。"""
    package = load_demo_package("foam_concrete_case")
    evidence = build_evidence(package)
    for item, lead in zip(evidence, package.literature_leads):
        expected = VerificationStatus(lead.status)
        assert item.verification_status is expected
        assert item.verification_status in (
            VerificationStatus.LEAD,
            VerificationStatus.PENDING,
        )
        assert item.extraction_summary == lead.summary


def test_literature_lead_source_location_traceable() -> None:
    """文献线索 Evidence 的来源定位指向数据包内条目，可追溯。"""
    package = load_demo_package("foam_concrete_case")
    evidence = build_evidence(package)
    lead_evidence = evidence[0]
    assert lead_evidence.source_location == (
        f"demo_data/{package.package_id}/package.json"
        "#literature_leads[lit-1]"
    )


def test_anomaly_evidence_keeps_synthetic_anomaly_semantics() -> None:
    """初始异常 Evidence 摘要保留合成异常语义，不写成真实实验结果。"""
    package = load_demo_package("foam_concrete_case")
    evidence = build_evidence(package)
    anomaly_evidence = evidence[-1]
    assert "合成异常" in anomaly_evidence.extraction_summary
    assert "真实实验结果" not in anomaly_evidence.extraction_summary
    assert anomaly_evidence.verification_status is VerificationStatus.PENDING
    assert anomaly_evidence.applicability_boundary == (
        package.initial_anomaly.not_experiment_result_note
    )


def test_anomaly_evidence_source_location_traceable() -> None:
    """初始异常 Evidence 的来源定位指向数据包内条目，可追溯。"""
    package = load_demo_package("foam_concrete_case")
    evidence = build_evidence(package)
    anomaly_evidence = evidence[-1]
    assert anomaly_evidence.source_location == (
        f"demo_data/{package.package_id}/package.json#initial_anomaly[anomaly-1]"
    )


def test_evidence_refs_stable_across_repeated_construction() -> None:
    """同一数据包版本重复构造时 Evidence 列表与引用稳定不变。"""
    package = load_demo_package("foam_concrete_case")
    first = [item.model_dump() for item in build_evidence(package)]
    second = [item.model_dump() for item in build_evidence(package)]
    assert first == second
    assert evidence_ref(package, "lit-1") == evidence_ref(package, "lit-1")
    assert evidence_ref(package, "anomaly-1") == evidence_ref(package, "anomaly-1")
