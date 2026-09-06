"""`app.demo_data` 稳定导出入口测试。

覆盖：从 `app.demo_data` 导入核心类型与函数、导出面不含测试 helper
或内部下划线名称、导入不触发 FastAPI/路由/文件读取副作用。
"""

import importlib
import subprocess
import sys
from pathlib import Path

import app.demo_data as demo_data

# 测试文件位于 <repo>/apps/api/tests/demo_data/，仓库根为 parents[4]。
_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_core_names_exported() -> None:
    """可从 `app.demo_data` 导入核心类型与函数。"""
    assert demo_data.DemoDataPackage is not None
    assert demo_data.DemoObjectBundle is not None
    assert demo_data.DemoIntegrityError is not None
    assert callable(demo_data.load_demo_package)
    assert callable(demo_data.build_demo_objects)
    assert callable(demo_data.reset_demo_objects)
    assert callable(demo_data.validate_demo_package_integrity)
    assert callable(demo_data.validate_demo_object_integrity)


def test_exports_do_not_include_test_helpers_or_privates() -> None:
    """导出面不含测试 helper 或下划线内部名称。"""
    assert "__all__" in vars(demo_data)
    for name in demo_data.__all__:
        assert not name.startswith("_")
    assert "make_object_id" not in demo_data.__all__
    assert "evidence_ref" not in demo_data.__all__


def test_exported_functions_are_module_level() -> None:
    """导出函数来自 demo_data 子模块，不是测试或临时对象。"""
    assert demo_data.load_demo_package.__module__ == "app.demo_data.loader"
    assert (
        demo_data.build_demo_objects.__module__ == "app.demo_data.object_factory"
    )
    assert demo_data.reset_demo_objects.__module__ == "app.demo_data.object_factory"
    assert (
        demo_data.validate_demo_package_integrity.__module__
        == "app.demo_data.integrity_guard"
    )
    assert (
        demo_data.validate_demo_object_integrity.__module__
        == "app.demo_data.integrity_guard"
    )


def test_import_does_not_load_fastapi_or_app_main() -> None:
    """全新解释器中导入 `app.demo_data` 不引入 FastAPI / starlette / app.main，不注册路由。

    全量套件中其他测试可能已导入 FastAPI，因此该检查必须在
    全新解释器（子进程）中执行。
    """
    code = (
        "import app.demo_data; "
        "import sys; "
        "assert 'fastapi' not in sys.modules; "
        "assert 'starlette' not in sys.modules; "
        "assert 'app.main' not in sys.modules; "
        "print('NO_FASTAPI')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT / "apps/api",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "NO_FASTAPI" in result.stdout


def test_fresh_interpreter_import_succeeds_without_side_effects() -> None:
    """全新解释器中导入 `app.demo_data` 成功（导入链不做文件读取）。"""
    code = (
        "import app.demo_data as d; "
        "assert callable(d.load_demo_package); "
        "assert callable(d.reset_demo_objects); "
        "print('IMPORT_OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT / "apps/api",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout


def test_module_is_importable_by_path() -> None:
    """`app.demo_data` 可通过 importlib 导入。"""
    module = importlib.import_module("app.demo_data")
    assert module.__name__ == "app.demo_data"
