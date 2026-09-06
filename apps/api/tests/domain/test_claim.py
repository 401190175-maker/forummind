"""`app.domain.schemas.claim` 候选科学主张对象契约测试。"""

import importlib

import pytest
from pydantic import ValidationError

from app.domain.schemas.claim import Claim
from app.domain.schemas.common import ClaimStatus, ObjectReference, ObjectType


def test_module_is_importable() -> None:
    """`app.domain.schemas.claim` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.claim")
    assert module.__name__ == "app.domain.schemas.claim"


def test_claim_minimal_construction() -> None:
    """Claim 可只凭可检验表述、预测、可推翻条件与 Claim 状态构造最小合法对象。"""
    claim = Claim(
        testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
        prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
        falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
        status=ClaimStatus.CANDIDATE,
    )
    assert claim.testable_statement == "泡沫混凝土抗压强度随气孔率升高而下降"
    assert claim.prediction == "气孔率从 30% 增至 50% 时抗压强度下降超过 40%"
    assert claim.falsification_condition == (
        "在 28 天标准养护下测得抗压强度未随气孔率升高而下降"
    )
    assert claim.status is ClaimStatus.CANDIDATE
    assert claim.project is None
    assert claim.research_question is None
    assert claim.proposer is None
    assert claim.applicability_boundary is None
    assert claim.supporting_evidence == []
    assert claim.opposing_evidence == []
    assert claim.uncertainty is None


def test_claim_expresses_full_semantics() -> None:
    """Claim 完整表达所属 Project、ResearchQuestion、提出者、可检验表述、适用边界、支持/反对证据、预测、可推翻条件、不确定性说明与状态。"""
    claim = Claim(
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        research_question=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id="rq-2026-001",
            version="v2",
        ),
        proposer=ObjectReference(object_type=ObjectType.AGENT_PROFILE, object_id="agent-phd-1"),
        testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
        applicability_boundary="仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天",
        supporting_evidence=[
            ObjectReference(
                object_type=ObjectType.EVIDENCE,
                object_id="ev-2026-001",
                version="v1",
            ),
        ],
        opposing_evidence=[
            ObjectReference(
                object_type=ObjectType.EVIDENCE,
                object_id="ev-2026-002",
                version="v1",
            ),
        ],
        prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
        falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
        uncertainty="不同发泡剂种类可能引入额外孔结构差异",
        status=ClaimStatus.SUPPORTED,
    )
    assert claim.project is not None
    assert claim.project.object_type is ObjectType.PROJECT
    assert claim.project.object_id == "proj-2026-001"
    assert claim.research_question is not None
    assert claim.research_question.object_type is ObjectType.RESEARCH_QUESTION
    assert claim.research_question.object_id == "rq-2026-001"
    assert claim.research_question.version == "v2"
    assert claim.proposer is not None
    assert claim.proposer.object_type is ObjectType.AGENT_PROFILE
    assert claim.proposer.object_id == "agent-phd-1"
    assert claim.testable_statement == "泡沫混凝土抗压强度随气孔率升高而下降"
    assert claim.applicability_boundary == "仅适用于废弃泥浆基泡沫混凝土，标准养护 28 天"
    assert [ref.object_id for ref in claim.supporting_evidence] == ["ev-2026-001"]
    assert claim.supporting_evidence[0].version == "v1"
    assert [ref.object_id for ref in claim.opposing_evidence] == ["ev-2026-002"]
    assert claim.opposing_evidence[0].version == "v1"
    assert claim.prediction == "气孔率从 30% 增至 50% 时抗压强度下降超过 40%"
    assert claim.falsification_condition == (
        "在 28 天标准养护下测得抗压强度未随气孔率升高而下降"
    )
    assert claim.uncertainty == "不同发泡剂种类可能引入额外孔结构差异"
    assert claim.status is ClaimStatus.SUPPORTED


def test_claim_missing_testable_statement_raises() -> None:
    """Claim 缺少可检验表述时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Claim(
            prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
            falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
            status=ClaimStatus.CANDIDATE,
        )


def test_claim_missing_prediction_raises() -> None:
    """Claim 缺少预测时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
            falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
            status=ClaimStatus.CANDIDATE,
        )


def test_claim_missing_falsification_condition_raises() -> None:
    """Claim 缺少可推翻条件时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
            prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
            status=ClaimStatus.CANDIDATE,
        )


def test_claim_missing_status_raises() -> None:
    """Claim 未定义 Claim 状态时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
            prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
            falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
        )


@pytest.mark.parametrize("testable_statement", ["", "   "])
def test_claim_blank_testable_statement_raises(testable_statement: str) -> None:
    """Claim 可检验表述不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement=testable_statement,
            prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
            falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
            status=ClaimStatus.CANDIDATE,
        )


@pytest.mark.parametrize("prediction", ["", "   "])
def test_claim_blank_prediction_raises(prediction: str) -> None:
    """Claim 预测不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
            prediction=prediction,
            falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
            status=ClaimStatus.CANDIDATE,
        )


@pytest.mark.parametrize("falsification_condition", ["", "   "])
def test_claim_blank_falsification_condition_raises(falsification_condition: str) -> None:
    """Claim 可推翻条件不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
            prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
            falsification_condition=falsification_condition,
            status=ClaimStatus.CANDIDATE,
        )


@pytest.mark.parametrize("status", ["approved", "final", "not-a-status"])
def test_claim_invalid_status_raises(status: str) -> None:
    """Claim 状态使用未定义值（含导师批准类）时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
            prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
            falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
            status=status,
        )


def test_claim_status_accepts_defined_value() -> None:
    """Claim 状态接受已定义枚举值。"""
    claim = Claim(
        testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
        prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
        falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
        status="weakened",
    )
    assert claim.status is ClaimStatus.WEAKENED


def test_claim_supporting_evidence_rejects_invalid_reference() -> None:
    """Claim 支持 Evidence 引用必须为合法对象引用。"""
    with pytest.raises(ValidationError):
        Claim(
            testable_statement="泡沫混凝土抗压强度随气孔率升高而下降",
            prediction="气孔率从 30% 增至 50% 时抗压强度下降超过 40%",
            falsification_condition="在 28 天标准养护下测得抗压强度未随气孔率升高而下降",
            status=ClaimStatus.CANDIDATE,
            supporting_evidence=[
                ObjectReference(object_type="not-an-object", object_id="ev-2026-001"),
            ],
        )


def test_claim_field_surface_avoids_forbidden_dimensions() -> None:
    """Claim 只包含契约字段，不包含投票胜负、导师决定、结论自动确认或覆盖式历史更新字段。"""
    assert set(Claim.model_fields) == {
        "testable_statement",
        "status",
        "project",
        "research_question",
        "proposer",
        "applicability_boundary",
        "supporting_evidence",
        "opposing_evidence",
        "prediction",
        "falsification_condition",
        "uncertainty",
    }
