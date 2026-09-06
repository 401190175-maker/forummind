"""`app.demo_data.integrity_guard` 数据包级完整性保护测试。

以真实合成数据包（`demo_data/foam_concrete_case/package.json`）为合法基线，
各负向用例通过深拷贝后注入违规内容，验证 guard 拒绝并给出可读信息。
"""

import importlib

import pytest

from app.demo_data.integrity_guard import (
    DemoIntegrityError,
    validate_demo_package_integrity,
)
from app.demo_data.loader import load_demo_package
from app.demo_data.package_schema import DemoDataPackage


def test_module_is_importable() -> None:
    """`app.demo_data.integrity_guard` 可被导入。"""
    module = importlib.import_module("app.demo_data.integrity_guard")
    assert module.__name__ == "app.demo_data.integrity_guard"


def _fresh_package() -> DemoDataPackage:
    """加载真实数据包并返回深拷贝，避免用例间互相污染。"""
    return load_demo_package("foam_concrete_case").model_copy(deep=True)


def test_valid_package_passes_integrity_guard() -> None:
    """合法静态数据包通过 integrity guard。"""
    validate_demo_package_integrity(_fresh_package())


def test_missing_demo_only_semantics_rejected() -> None:
    """合成声明缺少 demo-only 语义时拒绝。"""
    package = _fresh_package()
    package.synthetic_notice = "这是一份测试材料说明，与科研无关。"
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_package_integrity(package)
    assert "demo-only" in str(excinfo.value)


def test_missing_non_evidence_semantics_rejected() -> None:
    """合成声明缺少 non-evidence 语义时拒绝。"""
    package = _fresh_package()
    package.synthetic_notice = "本数据包仅用于演示流程。"
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_package_integrity(package)
    assert "non-evidence" in str(excinfo.value)


def test_lead_status_verified_rejected() -> None:
    """文献线索被标记为 verified 时拒绝（防御性检查：schema 之外的第二道防线）。"""
    package = _fresh_package()
    package.literature_leads[0].status = "verified"
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_package_integrity(package)
    assert "verified" in str(excinfo.value)
    assert "lead" in str(excinfo.value)


def test_anomaly_missing_synthetic_semantics_rejected() -> None:
    """初始异常缺少 synthetic anomaly 语义（is_synthetic_anomaly=False）时拒绝。"""
    package = _fresh_package()
    package.initial_anomaly.is_synthetic_anomaly = False
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_package_integrity(package)
    assert "synthetic anomaly" in str(excinfo.value)


@pytest.mark.parametrize(
    "connection_text",
    [
        "连接串 postgres://user:pass@localhost:5432/demo",
        "使用 sqlite:///data/real.db",
        "DATABASE_URL=mysql://root@127.0.0.1:3306/forummind",
        "redis://cache.internal:6379/0",
    ],
)
def test_db_connection_config_rejected(connection_text: str) -> None:
    """数据包内容出现真实数据库连接配置特征时拒绝。"""
    package = _fresh_package()
    package.experiment_constraints.equipment = connection_text
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_package_integrity(package)
    assert "数据库连接" in str(excinfo.value)


@pytest.mark.parametrize(
    "forbidden_phrase",
    [
        "该现象已证实与掺量相关",
        "本实验已证明强度下降",
        "该结果属于真实实验结果",
        "文献已证实该机理",
        "实验证明大孔比例增加",
    ],
)
def test_forbidden_conclusion_phrases_rejected(forbidden_phrase: str) -> None:
    """数据包内容出现科研结论式禁止性表述时拒绝。"""
    package = _fresh_package()
    package.research_direction.description = forbidden_phrase
    with pytest.raises(DemoIntegrityError) as excinfo:
        validate_demo_package_integrity(package)
    assert "禁止性表述" in str(excinfo.value)
