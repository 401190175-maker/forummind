"""`app.domain.schemas.evidence` 证据对象契约测试。"""

import importlib

import pytest
from pydantic import ValidationError

from app.domain.schemas.common import (
    DataSpace,
    ObjectReference,
    ObjectType,
    SourceType,
    VerificationStatus,
)
from app.domain.schemas.evidence import DataCategory, Evidence


def test_module_is_importable() -> None:
    """`app.domain.schemas.evidence` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.evidence")
    assert module.__name__ == "app.domain.schemas.evidence"


def test_evidence_minimal_construction() -> None:
    """Evidence 可只凭来源类型、数据类别、核查状态与适用边界构造最小合法对象。"""
    evidence = Evidence(
        source_type=SourceType.LITERATURE,
        data_category=DataCategory.TEXT,
        verification_status=VerificationStatus.PENDING,
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
    )
    assert evidence.source_type is SourceType.LITERATURE
    assert evidence.data_category is DataCategory.TEXT
    assert evidence.verification_status is VerificationStatus.PENDING
    assert evidence.applicability_boundary == "仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天"
    assert evidence.project is None
    assert evidence.source_location is None
    assert evidence.data_space is None
    assert evidence.materials is None
    assert evidence.samples is None
    assert evidence.methods is None
    assert evidence.conditions is None
    assert evidence.extraction_summary is None
    assert evidence.related_claims == []
    assert evidence.rejection_reason is None
    assert evidence.pending_reason is None


def test_evidence_expresses_full_semantics() -> None:
    """Evidence 完整表达所属 Project、来源类型、来源定位信息、数据类别、数据空间、材料、样品、方法、条件、提取内容摘要、核查状态、适用边界、关联 Claim 引用与拒绝原因或待核查原因。"""
    evidence = Evidence(
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        source_type=SourceType.EXPERIMENT,
        source_location="实验记录本 2026-03-15，编号 EXP-2026-007",
        data_space=DataSpace.REAL,
        data_category=DataCategory.NUMERIC,
        materials="废弃泥浆、发泡剂 A、P·O 42.5 水泥",
        samples="100×100×100 mm 泡沫混凝土试块 3 组",
        methods="参照 GB/T 50081 测定 28 天抗压强度",
        conditions="标准养护（20±2 ℃，相对湿度 ≥95%）",
        extraction_summary="气孔率 40% 的试块 28 天抗压强度为 3.2 MPa",
        verification_status=VerificationStatus.VERIFIED,
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        related_claims=[
            ObjectReference(
                object_type=ObjectType.CLAIM,
                object_id="claim-2026-001",
                version="v1",
            ),
        ],
    )
    assert evidence.project is not None
    assert evidence.project.object_type is ObjectType.PROJECT
    assert evidence.project.object_id == "proj-2026-001"
    assert evidence.source_type is SourceType.EXPERIMENT
    assert evidence.source_location == "实验记录本 2026-03-15，编号 EXP-2026-007"
    assert evidence.data_space is DataSpace.REAL
    assert evidence.data_category is DataCategory.NUMERIC
    assert evidence.materials == "废弃泥浆、发泡剂 A、P·O 42.5 水泥"
    assert evidence.samples == "100×100×100 mm 泡沫混凝土试块 3 组"
    assert evidence.methods == "参照 GB/T 50081 测定 28 天抗压强度"
    assert evidence.conditions == "标准养护（20±2 ℃，相对湿度 ≥95%）"
    assert evidence.extraction_summary == "气孔率 40% 的试块 28 天抗压强度为 3.2 MPa"
    assert evidence.verification_status is VerificationStatus.VERIFIED
    assert evidence.applicability_boundary == "仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天"
    assert [ref.object_id for ref in evidence.related_claims] == ["claim-2026-001"]
    assert evidence.related_claims[0].version == "v1"
    assert evidence.rejection_reason is None
    assert evidence.pending_reason is None


def test_evidence_missing_source_type_raises() -> None:
    """Evidence 缺少来源类型时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_missing_data_category_raises() -> None:
    """Evidence 缺少数据类别时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_missing_verification_status_raises() -> None:
    """Evidence 缺少核查状态时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=DataCategory.TEXT,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_missing_applicability_boundary_raises() -> None:
    """Evidence 缺少适用边界时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.PENDING,
        )


@pytest.mark.parametrize("applicability_boundary", ["", "   "])
def test_evidence_blank_applicability_boundary_raises(applicability_boundary: str) -> None:
    """Evidence 适用边界不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary=applicability_boundary,
        )


@pytest.mark.parametrize("source_type", ["fake-type", "not-a-source"])
def test_evidence_invalid_source_type_raises(source_type: str) -> None:
    """Evidence 来源类型使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=source_type,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_source_type_accepts_defined_value() -> None:
    """Evidence 来源类型接受已定义枚举值。"""
    evidence = Evidence(
        source_type="experiment",
        data_category=DataCategory.NUMERIC,
        verification_status=VerificationStatus.PENDING,
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
    )
    assert evidence.source_type is SourceType.EXPERIMENT


@pytest.mark.parametrize("verification_status", ["fake-status", "not-a-status"])
def test_evidence_invalid_verification_status_raises(verification_status: str) -> None:
    """Evidence 核查状态使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=DataCategory.TEXT,
            verification_status=verification_status,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_verification_status_accepts_defined_value() -> None:
    """Evidence 核查状态接受已定义枚举值。"""
    evidence = Evidence(
        source_type=SourceType.LITERATURE,
        data_category=DataCategory.TEXT,
        verification_status="pending",
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
    )
    assert evidence.verification_status is VerificationStatus.PENDING


@pytest.mark.parametrize("data_category", ["fake-category", "not-a-category"])
def test_evidence_invalid_data_category_raises(data_category: str) -> None:
    """Evidence 数据类别使用未定义值时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=data_category,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_data_category_accepts_defined_value() -> None:
    """Evidence 数据类别接受已定义枚举值。"""
    evidence = Evidence(
        source_type=SourceType.LITERATURE,
        data_category="numeric",
        verification_status=VerificationStatus.PENDING,
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
    )
    assert evidence.data_category is DataCategory.NUMERIC


def test_evidence_unlocatable_source_cannot_be_verified() -> None:
    """无法定位来源的 Evidence 不能被标记为已核查。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.VERIFIED,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_unlocatable_source_cannot_be_rejected() -> None:
    """无法定位来源的 Evidence 不能被标记为被拒绝。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.REJECTED,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_unlocatable_source_allows_lead() -> None:
    """无法定位来源的 Evidence 可标记为线索。"""
    evidence = Evidence(
        source_type=SourceType.LITERATURE,
        data_category=DataCategory.TEXT,
        verification_status=VerificationStatus.LEAD,
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
    )
    assert evidence.source_location is None
    assert evidence.verification_status is VerificationStatus.LEAD


def test_evidence_unlocatable_source_allows_pending() -> None:
    """无法定位来源的 Evidence 可标记为待核查。"""
    evidence = Evidence(
        source_type=SourceType.LITERATURE,
        data_category=DataCategory.TEXT,
        verification_status=VerificationStatus.PENDING,
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
    )
    assert evidence.source_location is None
    assert evidence.verification_status is VerificationStatus.PENDING


def test_evidence_verified_requires_source_location() -> None:
    """已核查的 Evidence 必须携带来源定位信息。"""
    evidence = Evidence(
        source_type=SourceType.EXPERIMENT,
        source_location="实验记录本 2026-03-15，编号 EXP-2026-007",
        data_category=DataCategory.NUMERIC,
        verification_status=VerificationStatus.VERIFIED,
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
    )
    assert evidence.source_location == "实验记录本 2026-03-15，编号 EXP-2026-007"
    assert evidence.verification_status is VerificationStatus.VERIFIED


@pytest.mark.parametrize("data_space", [None, DataSpace.REAL])
def test_evidence_synthetic_source_without_marker_raises(data_space: DataSpace | None) -> None:
    """合成 demo 材料未显式保留合成数据空间或合成数据类别时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.SYNTHETIC_DEMO,
            data_space=data_space,
            data_category=DataCategory.NUMERIC,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary="仅用于演示 ForumMind 流程的合成材料",
        )


def test_evidence_synthetic_source_with_synthetic_data_space_allowed() -> None:
    """合成 demo 材料显式保留合成数据空间时可构造。"""
    evidence = Evidence(
        source_type=SourceType.SYNTHETIC_DEMO,
        data_space=DataSpace.SYNTHETIC,
        data_category=DataCategory.NUMERIC,
        verification_status=VerificationStatus.PENDING,
        applicability_boundary="仅用于演示 ForumMind 流程的合成材料",
    )
    assert evidence.data_space is DataSpace.SYNTHETIC
    assert evidence.data_category is DataCategory.NUMERIC


def test_evidence_synthetic_source_with_synthetic_data_category_allowed() -> None:
    """合成 demo 材料显式保留合成数据类别时可构造。"""
    evidence = Evidence(
        source_type=SourceType.SYNTHETIC_DEMO,
        data_space=DataSpace.REAL,
        data_category=DataCategory.SYNTHETIC,
        verification_status=VerificationStatus.PENDING,
        applicability_boundary="仅用于演示 ForumMind 流程的合成材料",
    )
    assert evidence.data_space is DataSpace.REAL
    assert evidence.data_category is DataCategory.SYNTHETIC


@pytest.mark.parametrize("source_location", ["", "   "])
def test_evidence_blank_source_location_raises(source_location: str) -> None:
    """Evidence 来源定位信息不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            source_location=source_location,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        )


def test_evidence_related_claims_rejects_invalid_reference() -> None:
    """Evidence 关联 Claim 引用必须为合法对象引用。"""
    with pytest.raises(ValidationError):
        Evidence(
            source_type=SourceType.LITERATURE,
            data_category=DataCategory.TEXT,
            verification_status=VerificationStatus.PENDING,
            applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
            related_claims=[
                ObjectReference(object_type="not-an-object", object_id="claim-2026-001"),
            ],
        )


def test_evidence_field_surface_avoids_forbidden_dimensions() -> None:
    """Evidence 只包含契约字段，不包含文件解析、原始文件存储、向量 embedding 或证据自动升级字段。"""
    assert set(Evidence.model_fields) == {
        "project",
        "source_type",
        "source_location",
        "data_space",
        "data_category",
        "materials",
        "samples",
        "methods",
        "conditions",
        "extraction_summary",
        "verification_status",
        "applicability_boundary",
        "related_claims",
        "rejection_reason",
        "pending_reason",
    }
