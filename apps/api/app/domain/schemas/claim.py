"""Claim 候选科学主张对象契约。

仅定义候选科学主张的最小 Pydantic 校验模型：所属 Project、
所属 ResearchQuestion、提出者、可检验表述、适用边界、支持与反对
Evidence 引用、预测、可推翻条件、不确定性说明与 Claim 状态。
Claim 是候选科学主张，不表示导师批准或最终结论；
不包含投票胜负、导师决定、结论自动确认或覆盖式历史更新逻辑。
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from .common import ClaimStatus, ObjectReference


class Claim(BaseModel):
    """候选科学主张对象：固定可检验表述、提出者、证据引用、预测与可推翻条件。

    表达所属 Project、所属 ResearchQuestion、提出者、可检验表述、
    适用边界、支持与反对 Evidence 引用、预测、可推翻条件、
    不确定性说明与 Claim 状态；不表示导师批准或最终结论，
    不表达投票胜负、导师决定、结论自动确认或覆盖式历史更新。
    """

    testable_statement: Annotated[
        str, StringConstraints(min_length=1, strip_whitespace=True)
    ]  # 可检验表述
    status: ClaimStatus  # Claim 状态（候选科学主张的科研状态）
    project: ObjectReference | None = None  # 所属 Project
    research_question: ObjectReference | None = None  # 所属 ResearchQuestion
    proposer: ObjectReference | None = None  # 提出者引用
    applicability_boundary: str | None = None  # 适用边界
    supporting_evidence: list[ObjectReference] = Field(default_factory=list)  # 支持 Evidence 引用
    opposing_evidence: list[ObjectReference] = Field(default_factory=list)  # 反对 Evidence 引用
    prediction: Annotated[
        str, StringConstraints(min_length=1, strip_whitespace=True)
    ]  # 预测
    falsification_condition: Annotated[
        str, StringConstraints(min_length=1, strip_whitespace=True)
    ]  # 可推翻条件
    uncertainty: str | None = None  # 不确定性说明
