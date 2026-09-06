"""ResearchState 只读研究状态快照对象契约。

仅定义当前课题状态的只读版本快照的最小 Pydantic 校验模型：所属 Project、
当前 ResearchQuestion 引用、竞争性 Claim 引用、关键 Evidence 引用、
数据空间、证据缺口摘要、未决分歧摘要、待 PI 决定事项摘要、输入对象版本集合、
生成者与状态版本。
ResearchState 的核心规则是追加新版本，不覆盖旧版本——新快照以追加方式
生成，旧快照不被覆盖；当前阶段仅在 schema 层表达此语义，不实现持久化保证。
不包含 Memory 存储引擎、完整会议记录、状态自动推进规则或导师决定对象本身。
"""

from pydantic import BaseModel, Field

from .common import DataSpace, ObjectReference, VersionInfo


class ResearchState(BaseModel):
    """只读研究状态快照对象：固定当前问题、竞争性 Claim、关键 Evidence、证据缺口与输入版本集合。

    表达所属 Project、当前 ResearchQuestion 引用、竞争性 Claim 引用、
    关键 Evidence 引用、数据空间、证据缺口摘要、未决分歧摘要、待 PI 决定事项摘要、
    输入对象版本集合、生成者与状态版本；状态版本是只读快照版本，
    新状态以追加方式生成新快照，旧版本不被覆盖。
    不表达 Memory 存储引擎、完整会议记录、状态自动推进规则或导师决定对象本身。
    """

    project: ObjectReference  # 所属 Project
    current_research_question: ObjectReference  # 当前 ResearchQuestion 引用
    version: VersionInfo  # 状态版本（只读快照版本：追加新版本，不覆盖旧版本）
    data_space: DataSpace | None = None  # 数据空间（合成数据派生快照必须显式保留合成标记，不能伪装成真实数据）
    competing_claims: list[ObjectReference] = Field(default_factory=list)  # 竞争性 Claim 引用
    key_evidence: list[ObjectReference] = Field(default_factory=list)  # 关键 Evidence 引用
    evidence_gaps_summary: str | None = None  # 证据缺口摘要
    unresolved_disagreements_summary: str | None = None  # 未决分歧摘要
    pending_pi_decisions_summary: str | None = None  # 待 PI 决定事项摘要
    input_versions: list[ObjectReference] = Field(default_factory=list)  # 输入对象版本集合
    generated_by: ObjectReference | None = None  # 生成者引用
