"""`app.domain.schemas.research_question` 研究问题对象契约测试。"""

import importlib

import pytest
from pydantic import ValidationError

from app.domain.schemas.common import ObjectReference, ObjectType, VersionInfo
from app.domain.schemas.research_question import ResearchQuestion


def test_module_is_importable() -> None:
    """`app.domain.schemas.research_question` 可被导入。"""
    module = importlib.import_module("app.domain.schemas.research_question")
    assert module.__name__ == "app.domain.schemas.research_question"


def test_research_question_minimal_construction() -> None:
    """ResearchQuestion 可只凭现象或研究目标、材料体系与待解释事项构造最小合法对象。"""
    question = ResearchQuestion(
        phenomenon_or_objective="废弃泥浆基泡沫混凝土的抗压强度偏低",
        material_system="废弃泥浆、水泥、发泡剂",
        to_explain=["抗压强度偏低的机理"],
    )
    assert question.phenomenon_or_objective == "废弃泥浆基泡沫混凝土的抗压强度偏低"
    assert question.material_system == "废弃泥浆、水泥、发泡剂"
    assert question.to_explain == ["抗压强度偏低的机理"]
    assert question.project is None
    assert question.conditions is None
    assert question.to_decide == []
    assert question.constraints is None
    assert question.version is None


def test_research_question_expresses_full_semantics() -> None:
    """ResearchQuestion 完整表达所属 Project、现象/目标、材料条件、待解释/待决定事项、现实约束与版本关系。"""
    question = ResearchQuestion(
        project=ObjectReference(
            object_type=ObjectType.PROJECT,
            object_id="proj-2026-001",
        ),
        phenomenon_or_objective="废弃泥浆基泡沫混凝土抗压强度偏低",
        material_system="废弃泥浆、水泥、发泡剂",
        conditions="标准养护 28 天",
        to_explain=["抗压强度偏低的机理", "孔结构与强度的关系"],
        to_decide=["是否引入引气剂", "养护制度是否调整"],
        constraints="仅使用课题现有设备",
        version=VersionInfo(
            version="v2",
            previous_version_id=ObjectReference(
                object_type=ObjectType.RESEARCH_QUESTION,
                object_id="rq-2026-001",
                version="v1",
            ),
        ),
    )
    assert question.project is not None
    assert question.project.object_type is ObjectType.PROJECT
    assert question.project.object_id == "proj-2026-001"
    assert question.phenomenon_or_objective == "废弃泥浆基泡沫混凝土抗压强度偏低"
    assert question.material_system == "废弃泥浆、水泥、发泡剂"
    assert question.conditions == "标准养护 28 天"
    assert question.to_explain == ["抗压强度偏低的机理", "孔结构与强度的关系"]
    assert question.to_decide == ["是否引入引气剂", "养护制度是否调整"]
    assert question.constraints == "仅使用课题现有设备"
    assert question.version is not None
    assert question.version.version == "v2"
    assert question.version.previous_version_id is not None
    assert question.version.previous_version_id.object_type is ObjectType.RESEARCH_QUESTION
    assert question.version.previous_version_id.object_id == "rq-2026-001"
    assert question.version.previous_version_id.version == "v1"


def test_research_question_missing_phenomenon_raises() -> None:
    """ResearchQuestion 缺少现象或研究目标时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ResearchQuestion(
            material_system="废弃泥浆、水泥、发泡剂",
            to_explain=["抗压强度偏低的机理"],
        )


def test_research_question_missing_material_system_raises() -> None:
    """ResearchQuestion 缺少材料体系时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ResearchQuestion(
            phenomenon_or_objective="废弃泥浆基泡沫混凝土抗压强度偏低",
            to_explain=["抗压强度偏低的机理"],
        )


def test_research_question_missing_to_explain_raises() -> None:
    """ResearchQuestion 缺少待解释事项时触发 ValidationError。"""
    with pytest.raises(ValidationError):
        ResearchQuestion(
            phenomenon_or_objective="废弃泥浆基泡沫混凝土抗压强度偏低",
            material_system="废弃泥浆、水泥、发泡剂",
        )


@pytest.mark.parametrize("phenomenon_or_objective", ["", "   "])
def test_research_question_blank_phenomenon_raises(phenomenon_or_objective: str) -> None:
    """ResearchQuestion 现象或研究目标不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        ResearchQuestion(
            phenomenon_or_objective=phenomenon_or_objective,
            material_system="废弃泥浆、水泥、发泡剂",
            to_explain=["抗压强度偏低的机理"],
        )


@pytest.mark.parametrize("material_system", ["", "   "])
def test_research_question_blank_material_system_raises(material_system: str) -> None:
    """ResearchQuestion 材料体系不允许为空或纯空白。"""
    with pytest.raises(ValidationError):
        ResearchQuestion(
            phenomenon_or_objective="废弃泥浆基泡沫混凝土抗压强度偏低",
            material_system=material_system,
            to_explain=["抗压强度偏低的机理"],
        )


def test_research_question_empty_to_explain_raises() -> None:
    """ResearchQuestion 待解释事项列表不允许为空。"""
    with pytest.raises(ValidationError):
        ResearchQuestion(
            phenomenon_or_objective="废弃泥浆基泡沫混凝土抗压强度偏低",
            material_system="废弃泥浆、水泥、发泡剂",
            to_explain=[],
        )


def test_research_question_field_surface_avoids_forbidden_dimensions() -> None:
    """ResearchQuestion 只包含契约字段，不包含自动拆题逻辑、Agent 生成过程或 PI 裁决字段。"""
    assert set(ResearchQuestion.model_fields) == {
        "project",
        "phenomenon_or_objective",
        "material_system",
        "conditions",
        "to_explain",
        "to_decide",
        "constraints",
        "version",
    }
