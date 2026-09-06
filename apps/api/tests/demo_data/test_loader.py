"""`app.demo_data.loader` 静态数据包 loader 测试。

覆盖真实数据包读取（不 monkeypatch）、文件缺失、JSON 解析失败、
schema 校验失败与非法 package_id 拒绝等路径；负向用例通过
monkeypatch `DEMO_DATA_ROOT` 到 `tmp_path` 隔离，不触碰仓库真实数据。
"""

import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.demo_data import loader as loader_module
from app.demo_data.loader import (
    DemoDataError,
    DemoPackageInvalidIdError,
    DemoPackageNotFoundError,
    DemoPackageParseError,
    DemoPackageValidationError,
    load_demo_package,
)
from app.demo_data.package_schema import DemoDataPackage


def build_minimal_package() -> dict[str, object]:
    """构造一份最小合法数据包（内存字典，键与接口契约一一对应）。"""
    return {
        "package_id": "schema_test",
        "version": "0.1.0",
        "label": "测试数据包",
        "synthetic_notice": "仅用于测试的合成声明",
        "research_direction": {
            "title": "测试方向",
            "description": "测试描述",
            "material_system": "测试材料体系",
            "phenomenon_or_objective": "测试现象",
            "to_explain": ["测试待解释事项"],
        },
        "literature_leads": [
            {
                "local_key": "lit-1",
                "title": "测试线索",
                "summary": "测试摘要",
                "status": "lead",
                "note": "测试备注",
            }
        ],
        "experiment_constraints": {
            "equipment": "测试设备",
            "timeline": "1 周",
            "samples": "测试样品",
            "cost": "测试成本",
            "measurable_indicators": ["测试指标"],
            "safety_boundary": "测试安全边界",
        },
        "initial_anomaly": {
            "local_key": "anomaly-1",
            "title": "测试异常",
            "description": "测试异常描述",
            "is_synthetic_anomaly": True,
            "not_experiment_result_note": "测试声明",
        },
        "agent_profiles": [
            {
                "local_key": "agent-1",
                "name": "测试 Agent",
                "role": "master_student",
                "primary_ability": "测试能力",
                "allowed_data_spaces": ["synthetic"],
            }
        ],
        "initial_tasks": [
            {
                "local_key": "task-1",
                "title": "测试任务",
                "description": "测试任务描述",
                "assigner": "agent-1",
                "assignee": "agent-1",
                "expected_output_object_type": "evidence",
                "input_local_keys": ["lit-1"],
                "status": "pending",
            }
        ],
        "expected_initial_state": {
            "summary": "测试状态摘要",
            "key_evidence_local_keys": ["lit-1"],
            "evidence_gaps_summary": "测试缺口",
            "unresolved_disagreements_summary": "测试分歧",
        },
        "reset_policy": {
            "scope": "仅内存重建",
            "determinism": "确定性重建",
            "allowed_spaces": ["synthetic"],
        },
        "integrity_rules": ["测试完整性规则"],
    }


def test_module_is_importable() -> None:
    """`app.demo_data.loader` 可被导入。"""
    module = importlib.import_module("app.demo_data.loader")
    assert module.__name__ == "app.demo_data.loader"


def test_load_demo_package_importable() -> None:
    """`load_demo_package` 可从 `app.demo_data.loader` 导入。"""
    assert load_demo_package.__name__ == "load_demo_package"


def test_exceptions_form_common_hierarchy() -> None:
    """全部 loader 异常继承 `DemoDataError` 基类，构成统一层级。"""
    for exc_type in (
        DemoPackageNotFoundError,
        DemoPackageParseError,
        DemoPackageValidationError,
        DemoPackageInvalidIdError,
    ):
        assert issubclass(exc_type, DemoDataError)


def test_load_real_foam_concrete_case() -> None:
    """读取真实数据包文件返回 `DemoDataPackage` 实例，关键字段与接口契约一致。"""
    package = load_demo_package("foam_concrete_case")
    assert isinstance(package, DemoDataPackage)
    assert package.package_id == "foam_concrete_case"
    assert package.version == "0.1.0"
    assert package.synthetic_notice.startswith("本数据包仅用于演示流程")


def test_unknown_package_raises_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未知 package_id 抛出 `DemoPackageNotFoundError`，信息包含 package id 与期望路径。"""
    monkeypatch.setattr(loader_module, "DEMO_DATA_ROOT", tmp_path)
    with pytest.raises(DemoPackageNotFoundError) as excinfo:
        load_demo_package("no_such_package")
    message = str(excinfo.value)
    assert "no_such_package" in message
    assert str(tmp_path / "no_such_package" / "package.json") in message


def test_invalid_json_raises_parse_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """package.json 内容不是合法 JSON 时抛出 `DemoPackageParseError`，信息包含文件路径与解析摘要。"""
    package_dir = tmp_path / "bad_json"
    package_dir.mkdir()
    (package_dir / "package.json").write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(loader_module, "DEMO_DATA_ROOT", tmp_path)
    with pytest.raises(DemoPackageParseError) as excinfo:
        load_demo_package("bad_json")
    message = str(excinfo.value)
    assert str(package_dir / "package.json") in message
    assert "Expecting" in message  # 底层 JSONDecodeError 摘要被保留


def test_schema_invalid_package_raises_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """缺少 synthetic_notice 的合法 JSON 抛出 `DemoPackageValidationError`，信息保留 Pydantic 校验详情。"""
    package_dir = tmp_path / "schema_bad"
    package_dir.mkdir()
    data = build_minimal_package()
    del data["synthetic_notice"]
    (package_dir / "package.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(loader_module, "DEMO_DATA_ROOT", tmp_path)
    with pytest.raises(DemoPackageValidationError) as excinfo:
        load_demo_package("schema_bad")
    assert "synthetic_notice" in str(excinfo.value)
    assert isinstance(excinfo.value.validation_error, ValidationError)


@pytest.mark.parametrize(
    "package_id",
    ["../evil", "a/b", "a\\b", ""],
)
def test_invalid_package_id_rejected_before_filesystem_access(
    package_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """含路径分隔符、`..` 或为空的 package_id 直接抛出 `DemoPackageInvalidIdError`，不访问文件系统。"""
    monkeypatch.setattr(loader_module, "DEMO_DATA_ROOT", tmp_path)
    with pytest.raises(DemoPackageInvalidIdError):
        load_demo_package(package_id)
