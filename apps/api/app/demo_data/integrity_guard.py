"""Demo 数据包完整性保护规则。

集中表达合成数据边界（设计 §2.6、§8.1、§8.2）：校验已加载的
`DemoDataPackage` 保留 synthetic/demo-only/non-evidence 语义，拒绝
合成文献伪装成已核查证据、拒绝合成异常伪装成真实实验结果，拒绝
数据包中出现真实数据库连接配置与科研结论式禁止性表述。

本模块不访问网络、不访问数据库、不调用 LLM，只做内存中的语义检查；
后续扩展到 API、数据库和 Memory 层时作为可复用的安全边界入口。
"""

import re

from app.demo_data.object_factory import DemoObjectBundle
from app.demo_data.package_schema import DemoDataPackage
from app.domain.schemas import DataSpace, SourceType, VerificationStatus

# 合成声明中的 demo-only 语义标记（大小写不敏感，命中任一即可）。
_DEMO_ONLY_MARKERS: tuple[str, ...] = (
    "demo-only",
    "仅用于演示",
    "只用于演示",
    "仅作演示",
    "演示流程",
    "演示用途",
)

# 合成声明中的 non-evidence 语义标记（大小写不敏感，命中任一即可）。
_NON_EVIDENCE_MARKERS: tuple[str, ...] = (
    "non-evidence",
    "非证据",
    "不是科研证据",
    "不作为科研证据",
    "非科研证据",
    "不代表真实实验",
    "不代表真实文献",
)

# 真实数据库连接配置特征：以 URL scheme 与常见配置键识别，大小写不敏感。
_DB_CONNECTION_PATTERNS: tuple[str, ...] = (
    r"postgres(?:ql)?://",
    r"mysql://",
    r"sqlite://",
    r"mongodb(?:\+srv)?://",
    r"redis://",
    r"rediss://",
    r"oracle://",
    r"mssql://",
    r"database_url",
    r"db_host",
    r"db_password",
    r"connection_string",
)

# 容易误导为真实科研结论的禁止性表述（大小写不敏感）。
_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "已证实",
    "已证明",
    "实验证明",
    "文献已证实",
    "经实验证实",
    "真实实验结果",
    "已被证实",
    "已经证明",
)

# 文献线索允许的核查状态：只能表达为线索或待核查材料，绝不能是已核查。
_ALLOWED_LEAD_STATUSES: frozenset[str] = frozenset({"lead", "pending"})


class DemoIntegrityError(Exception):
    """Demo 数据包完整性违规：合成边界被破坏时抛出。"""


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    """text 是否包含任一标记（大小写不敏感）。"""
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def validate_demo_package_integrity(package: DemoDataPackage) -> None:
    """校验数据包级 synthetic/demo-only/non-evidence 语义，违规时抛出 `DemoIntegrityError`。

    检查项：

    - `synthetic_notice` 必须同时包含 demo-only 与 non-evidence 语义。
    - 文献线索的核查状态只能是 `lead` 或 `pending`，不能是 `verified`。
    - 初始异常必须保留 synthetic anomaly 语义（`is_synthetic_anomaly` 为真）。
    - 数据包整体内容不得出现真实数据库连接配置特征。
    - 数据包整体内容不得出现科研结论式禁止性表述。
    """
    if not _contains_any(package.synthetic_notice, _DEMO_ONLY_MARKERS):
        raise DemoIntegrityError(
            "合成声明缺少 demo-only 语义：synthetic_notice 必须明确声明仅用于演示"
        )
    if not _contains_any(package.synthetic_notice, _NON_EVIDENCE_MARKERS):
        raise DemoIntegrityError(
            "合成声明缺少 non-evidence 语义：synthetic_notice 必须明确声明不是科研证据"
        )

    for lead in package.literature_leads:
        if lead.status not in _ALLOWED_LEAD_STATUSES:
            raise DemoIntegrityError(
                f"文献线索不能标记为已核查证据: local_key={lead.local_key!r}，"
                f"status={lead.status!r}（只允许 lead 或 pending）"
            )

    if not package.initial_anomaly.is_synthetic_anomaly:
        raise DemoIntegrityError(
            "初始异常缺少 synthetic anomaly 语义：is_synthetic_anomaly 必须为 true，"
            "合成异常不能伪装成真实实验结果"
        )

    serialized = package.model_dump_json()
    for pattern in _DB_CONNECTION_PATTERNS:
        if re.search(pattern, serialized, re.IGNORECASE):
            raise DemoIntegrityError(
                f"数据包内容出现真实数据库连接配置特征: {pattern!r}，"
                "合成数据包不得携带真实数据库连接"
            )
    for phrase in _FORBIDDEN_PHRASES:
        if phrase.lower() in serialized.lower():
            raise DemoIntegrityError(
                f"数据包内容出现科研结论式禁止性表述: {phrase!r}"
            )


def validate_demo_object_integrity(bundle: DemoObjectBundle) -> None:
    """校验派生对象集合的 synthetic 边界，违规时抛出 `DemoIntegrityError`（设计 §7.3、§8.1、§8.2）。

    检查项：

    - `Project.data_space` 必须是 `DataSpace.SYNTHETIC`。
    - `ResearchState.data_space` 必须是 `DataSpace.SYNTHETIC`。
    - 每个 demo `Evidence` 必须保留 `DataSpace.SYNTHETIC`。
    - 每个 demo `Evidence` 的 `source_type` 必须是 `SourceType.SYNTHETIC_DEMO`。
    - 文献线索 Evidence 不得被标记为 `VerificationStatus.VERIFIED`。
    """
    if bundle.project.data_space is not DataSpace.SYNTHETIC:
        raise DemoIntegrityError(
            "派生 Project 不是 synthetic：data_space 必须是 DataSpace.SYNTHETIC"
        )
    if bundle.research_state.data_space is not DataSpace.SYNTHETIC:
        raise DemoIntegrityError(
            "派生 ResearchState 不是 synthetic：data_space 必须是 DataSpace.SYNTHETIC"
        )
    for evidence in bundle.evidence:
        if evidence.data_space is not DataSpace.SYNTHETIC:
            raise DemoIntegrityError(
                f"demo Evidence 丢失合成标记: source_location={evidence.source_location!r}，"
                "data_space 必须是 DataSpace.SYNTHETIC"
            )
        if evidence.source_type is not SourceType.SYNTHETIC_DEMO:
            raise DemoIntegrityError(
                f"demo Evidence 来源类型错误: source_location={evidence.source_location!r}，"
                "source_type 必须是 SourceType.SYNTHETIC_DEMO"
            )
        if (
            "literature_leads" in (evidence.source_location or "")
            and evidence.verification_status is VerificationStatus.VERIFIED
        ):
            raise DemoIntegrityError(
                f"合成文献线索被标记为已核查证据: source_location={evidence.source_location!r}，"
                "verification_status 不能是 VerificationStatus.VERIFIED"
            )
