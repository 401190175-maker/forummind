"""`app.domain.schemas.research_state` 只读研究状态快照对象契约测试。"""

import importlib

import pytest
from pydantic import ValidationError

from app.domain.schemas.common import DataSpace, ObjectReference, ObjectType, VersionInfo
from app.domain.schemas.research_state import ResearchState


def test_module_is_importable() -> None:
    """`app.domain.schemas.research_state` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.research_state")
    assert module.__name__ == "app.domain.schemas.research_state"


def test_research_state_minimal_construction() -> None:
    """ResearchState 可只凭所属 Project、当前 ResearchQuestion 引用与状态版本构造最小合法对象。"""
    state = ResearchState(
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        current_research_question=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id="rq-2026-001",
        ),
        version=VersionInfo(version="v1"),
    )
    assert state.project is not None
    assert state.project.object_type is ObjectType.PROJECT
    assert state.project.object_id == "proj-2026-001"
    assert state.current_research_question is not None
    assert state.current_research_question.object_type is ObjectType.RESEARCH_QUESTION
    assert state.current_research_question.object_id == "rq-2026-001"
    assert state.version.version == "v1"
    assert state.version.previous_version_id is None
    assert state.data_space is None
    assert state.competing_claims == []
    assert state.key_evidence == []
    assert state.evidence_gaps_summary is None
    assert state.unresolved_disagreements_summary is None
    assert state.pending_pi_decisions_summary is None
    assert state.input_versions == []
    assert state.generated_by is None


def test_research_state_expresses_full_semantics() -> None:
    """ResearchState 完整表达所属 Project、当前 ResearchQuestion、竞争性 Claim、关键 Evidence、数据空间、摘要、输入版本、生成者与状态版本。"""
    state = ResearchState(
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        current_research_question=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id="rq-2026-001",
            version="v2",
        ),
        competing_claims=[
            ObjectReference(
                object_type=ObjectType.CLAIM,
                object_id="claim-2026-001",
                version="v1",
            ),
            ObjectReference(
                object_type=ObjectType.CLAIM,
                object_id="claim-2026-002",
                version="v1",
            ),
        ],
        key_evidence=[
            ObjectReference(
                object_type=ObjectType.EVIDENCE,
                object_id="ev-2026-001",
                version="v1",
            ),
        ],
        data_space=DataSpace.REAL,
        evidence_gaps_summary="缺少气孔率与抗压强度关系的原位观测数据",
        unresolved_disagreements_summary="关于引气剂对孔结构影响的机理存在分歧",
        pending_pi_decisions_summary="待 PI 决定是否引入引气剂",
        input_versions=[
            ObjectReference(
                object_type=ObjectType.RESEARCH_QUESTION,
                object_id="rq-2026-001",
                version="v2",
            ),
            ObjectReference(
                object_type=ObjectType.CLAIM,
                object_id="claim-2026-001",
                version="v1",
            ),
            ObjectReference(
                object_type=ObjectType.EVIDENCE,
                object_id="ev-2026-001",
                version="v1",
            ),
        ],
        generated_by=ObjectReference(
            object_type=ObjectType.AGENT_PROFILE,
            object_id="agent-phd-1",
        ),
        version=VersionInfo(
            version="v2",
            previous_version_id=ObjectReference(
                object_type=ObjectType.RESEARCH_STATE,
                object_id="rs-2026-001",
                version="v1",
            ),
        ),
    )
    assert state.project is not None
    assert state.project.object_type is ObjectType.PROJECT
    assert state.project.object_id == "proj-2026-001"
    assert state.current_research_question is not None
    assert state.current_research_question.object_type is ObjectType.RESEARCH_QUESTION
    assert state.current_research_question.object_id == "rq-2026-001"
    assert state.current_research_question.version == "v2"
    assert [ref.object_id for ref in state.competing_claims] == [
        "claim-2026-001",
        "claim-2026-002",
    ]
    assert state.competing_claims[0].version == "v1"
    assert state.competing_claims[1].version == "v1"
    assert [ref.object_id for ref in state.key_evidence] == ["ev-2026-001"]
    assert state.key_evidence[0].version == "v1"
    assert state.data_space is DataSpace.REAL
    assert state.evidence_gaps_summary == "缺少气孔率与抗压强度关系的原位观测数据"
    assert state.unresolved_disagreements_summary == "关于引气剂对孔结构影响的机理存在分歧"
    assert state.pending_pi_decisions_summary == "待 PI 决定是否引入引气剂"
    assert [ref.object_id for ref in state.input_versions] == [
        "rq-2026-001",
        "claim-2026-001",
        "ev-2026-001",
    ]
    assert state.input_versions[0].version == "v2"
    assert state.input_versions[1].version == "v1"
    assert state.input_versions[2].version == "v1"
    assert state.generated_by is not None
    assert state.generated_by.object_type is ObjectType.AGENT_PROFILE
    assert state.generated_by.object_id == "agent-phd-1"
    assert state.version.version == "v2"
    assert state.version.previous_version_id is not None
    assert state.version.previous_version_id.object_type is ObjectType.RESEARCH_STATE
    assert state.version.previous_version_id.object_id == "rs-2026-001"
    assert state.version.previous_version_id.version == "v1"


def test_research_state_synthetic_snapshot_keeps_synthetic_marker() -> None:
    """合成输入派生出的 ResearchState 快照必须显式保留合成数据空间标记，不能伪装成真实数据。"""
    state = ResearchState(
        project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
        current_research_question=ObjectReference(
            object_type=ObjectType.RESEARCH_QUESTION,
            object_id="rq-2026-001",
        ),
        version=VersionInfo(version="v1"),
        data_space=DataSpace.SYNTHETIC,
    )
    assert state.data_space is DataSpace.SYNTHETIC
    assert state.model_dump()["data_space"] == "synthetic"
    round_tripped = ResearchState.model_validate(state.model_dump())
    assert round_tripped.data_space is DataSpace.SYNTHETIC


def test_research_state_missing_project_raises() -> None:
    """ResearchState 缺少所属 Project 时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ResearchState(
            current_research_question=ObjectReference(
                object_type=ObjectType.RESEARCH_QUESTION,
                object_id="rq-2026-001",
            ),
            version=VersionInfo(version="v1"),
        )


def test_research_state_missing_current_research_question_raises() -> None:
    """ResearchState 缺少当前 ResearchQuestion 引用时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ResearchState(
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            version=VersionInfo(version="v1"),
        )


def test_research_state_missing_version_raises() -> None:
    """ResearchState 缺少状态版本时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ResearchState(
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            current_research_question=ObjectReference(
                object_type=ObjectType.RESEARCH_QUESTION,
                object_id="rq-2026-001",
            ),
        )


def test_research_state_competing_claims_rejects_invalid_reference() -> None:
    """ResearchState 竞争性 Claim 引用必须为合法对象引用。"""
    with pytest.raises(ValidationError):
        ResearchState(
            project=ObjectReference(object_type=ObjectType.PROJECT, object_id="proj-2026-001"),
            current_research_question=ObjectReference(
                object_type=ObjectType.RESEARCH_QUESTION,
                object_id="rq-2026-001",
            ),
            version=VersionInfo(version="v1"),
            competing_claims=[
                ObjectReference(object_type="not-an-object", object_id="claim-2026-001"),
            ],
        )


def test_research_state_field_surface_avoids_forbidden_dimensions() -> None:
    """ResearchState 只包含契约字段，不包含 Memory 存储引擎、完整会议记录、状态自动推进规则或导师决定对象字段。"""
    assert set(ResearchState.model_fields) == {
        "project",
        "current_research_question",
        "competing_claims",
        "key_evidence",
        "evidence_gaps_summary",
        "unresolved_disagreements_summary",
        "pending_pi_decisions_summary",
        "input_versions",
        "generated_by",
        "data_space",
        "version",
    }
