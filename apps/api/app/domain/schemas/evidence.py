"""Evidence 证据对象契约。

仅定义证据对象的最小 Pydantic 校验模型：所属 Project、来源类型、
来源定位信息、数据类别、数据空间、材料、样品、方法、条件、
提取内容摘要、核查状态、适用边界、关联 Claim 引用与拒绝原因或
待核查原因。Evidence 是有来源和边界的证据，不是模型生成文本；
不包含文件解析过程、原始文件存储、向量 embedding 或证据自动升级
为正式结论的逻辑。
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from .common import DataSpace, ObjectReference, SourceType, VerificationStatus


class DataCategory(StrEnum):
    """数据类别：Evidence 承载数据的类型。

    合成数据必须显式保留合成数据空间或合成数据类别，
    防止合成数据伪装成真实数据。
    """

    NUMERIC = "numeric"  # 数值数据
    TEXT = "text"  # 文本资料
    IMAGE = "image"  # 图像资料
    TIME_SERIES = "time_series"  # 时间序列
    SYNTHETIC = "synthetic"  # 合成数据


class Evidence(BaseModel):
    """证据对象：固定来源、数据类别、核查状态、材料条件和适用边界。

    表达所属 Project、来源类型、来源定位信息、数据类别、数据空间、
    材料、样品、方法、条件、提取内容摘要、核查状态、适用边界、
    关联 Claim 引用与拒绝原因或待核查原因；
    不表达文件解析过程、原始文件存储、向量 embedding 或证据自动
    升级为正式结论的逻辑。
    """

    source_type: SourceType  # 来源类型
    data_category: DataCategory  # 数据类别
    verification_status: VerificationStatus  # 核查状态
    applicability_boundary: Annotated[
        str, StringConstraints(min_length=1, strip_whitespace=True)
    ]  # 适用边界
    project: ObjectReference | None = None  # 所属 Project
    source_location: Annotated[
        str, StringConstraints(min_length=1, strip_whitespace=True)
    ] | None = None  # 来源定位信息
    data_space: DataSpace | None = None  # 数据空间
    materials: str | None = None  # 材料
    samples: str | None = None  # 样品
    methods: str | None = None  # 方法
    conditions: str | None = None  # 条件
    extraction_summary: str | None = None  # 提取内容摘要
    related_claims: list[ObjectReference] = Field(default_factory=list)  # 关联 Claim 引用
    rejection_reason: str | None = None  # 拒绝原因
    pending_reason: str | None = None  # 待核查原因

    @model_validator(mode="after")
    def _unlocatable_source_stays_unverified(self) -> "Evidence":
        """无法定位来源的 Evidence 只能标记为线索或待核查，不能被标记为已核查或被拒绝。"""
        if self.source_location is None and self.verification_status not in (
            VerificationStatus.LEAD,
            VerificationStatus.PENDING,
        ):
            raise ValueError(
                "缺少来源定位信息的 Evidence 只能标记为线索或待核查，"
                "不能标记为已核查或被拒绝"
            )
        return self

    @model_validator(mode="after")
    def _synthetic_data_keeps_synthetic_marker(self) -> "Evidence":
        """合成数据必须显式保留合成数据空间或合成数据类别，不能伪装成真实数据。"""
        if (
            self.source_type is SourceType.SYNTHETIC_DEMO
            and self.data_space is not DataSpace.SYNTHETIC
            and self.data_category is not DataCategory.SYNTHETIC
        ):
            raise ValueError(
                "合成 demo 材料必须显式保留合成数据空间或合成数据类别，"
                "不能伪装成真实数据"
            )
        return self
