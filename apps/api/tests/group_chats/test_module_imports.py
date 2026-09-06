"""课题组 API 模块包结构导入测试（Task 1）。

覆盖：`app.api.group_chats` 与 `app.group_chats` 可导入；
router 暂不注册除 `POST /group-chats` 以外的任何路径；
全新解释器中导入 `app.group_chats` 不引入 FastAPI app、
不读取 demo package、不访问网络与数据库。

注：demo package 是否被“读取”的副作用检查由 Task 16 的
导出入口测试（test_group_chats_exports.py）承担；本文件只保证
导入链本身干净（不引入 FastAPI / app.main / app.demo_data）。
"""

import importlib
import subprocess
import sys
from pathlib import Path

from app.api.group_chats import router as group_chats_router

# 测试文件位于 <repo>/apps/api/tests/group_chats/，仓库根为 parents[4]。
_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_app_api_group_chats_importable() -> None:
    """可从 `app.api.group_chats` 导入 router。"""
    module = importlib.import_module("app.api.group_chats")
    assert module.__name__ == "app.api.group_chats"
    assert group_chats_router is not None


def test_app_group_chats_importable() -> None:
    """可从 `app.group_chats` 导入包。"""
    module = importlib.import_module("app.group_chats")
    assert module.__name__ == "app.group_chats"


def test_group_chats_router_registers_no_other_paths() -> None:
    """router 只注册 allowlist 内的路径：POST /group-chats + demo-safe 消息/澄清路由。"""
    expected = {
        "/group-chats": {"GET", "POST"},
        "/group-chats/{group_chat_id}": {"GET", "DELETE"},
        "/group-chats/{group_chat_id}/meeting-schedule": {"GET", "PUT"},
        "/group-chats/{group_chat_id}/messages": {"POST", "GET"},
        "/group-chats/{group_chat_id}/task-clarifications": {"POST", "GET"},
        "/group-chats/{group_chat_id}/task-clarifications/{clarification_id}/answers": {"POST"},
        "/group-chats/{group_chat_id}/task-clarifications/{clarification_id}/formal-task": {"POST"},
        "/group-chats/{group_chat_id}/members/{member_id}/configuration": {"PATCH"},
    }
    actual: dict[str, set[str]] = {}
    for route in group_chats_router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        assert path in expected, f"未设计路由: {path}"
        assert methods and len(methods) == 1, f"路由方法异常: {path} {methods}"
        actual.setdefault(path, set()).update(methods)  # type: ignore[arg-type]
    assert actual == expected


def test_import_app_group_chats_without_fastapi_or_side_effects() -> None:
    """全新解释器中导入 `app.group_chats` 不引入 FastAPI / app.main。

    注：`app.group_chats` 自 Task 16 起会导入 `app.demo_data` 模块
    （DTO 与创建服务依赖其类型），但模块导入本身不读取 package.json；
    文件读取只发生在 `load_demo_package` 调用时，导入无副作用检查
    由 test_group_chats_exports.py 承担。
    """
    code = (
        "import app.group_chats; "
        "import sys; "
        "assert 'fastapi' not in sys.modules; "
        "assert 'starlette' not in sys.modules; "
        "assert 'app.main' not in sys.modules; "
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
