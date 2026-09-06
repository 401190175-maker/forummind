"""ResearchQuestion 研究问题对象契约。

仅定义研究问题对象的最小 Pydantic 校验模型：所属 Project、
现象或研究目标、材料体系、实验或现实条件、待解释事项、
待决定事项、现实约束与问题版本关系。
不包含自动拆题逻辑、Agent 生成过程或 PI 最终裁决字段。
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from .common import ObjectReference, VersionInfo


class ResearchQuestion(BaseModel):
    """研究问题对象：被收束后的研究问题，承接用户模糊方向或实验异常。

    表达所属 Project、现象或研究目标、材料体系、实验或现实条件、
    待解释事项、待决定事项、现实约束与问题版本关系；
    不表达自动拆题逻辑、Agent 生成过程或 PI 最终裁决。
    """

    phenomenon_or_objective: Annotated[
        str, StringConstraints(min_length=1, strip_whitespace=True)
    ]  # 现象或研究目标
    material_system: Annotated[
        str, StringConstraints(min_length=1, strip_whitespace=True)
    ]  # 材料体系
    to_explain: list[str] = Field(min_length=1)  # 待解释事项
    project: ObjectReference | None = None  # 所属 Project
    conditions: str | None = None  # 实验或现实条件
    to_decide: list[str] = Field(default_factory=list)  # 待决定事项
    constraints: str | None = None  # 现实约束
    version: VersionInfo | None = None  # 问题版本关系
