"""`app.group_chats` 稳定导出入口测试（Task 16）。

覆盖：从 `app.group_chats` 导入核心类型与函数、导出面不含测试
helper 或内部下划线名称、导入不注册 FastAPI 路由、不读取 demo
package、不访问网络与数据库。
"""

import importlib
import subprocess
import sys
from pathlib import Path

import app.group_chats as group_chats

# 测试文件位于 <repo>/apps/api/tests/group_chats/，仓库根为 parents[4]。
_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_core_names_exported() -> None:
    """可从 `app.group_chats` 导入核心请求/响应类型与创建服务。"""
    assert group_chats.CreateGroupChatRequest is not None
    assert group_chats.CreateGroupChatResponse is not None
    assert callable(group_chats.create_group_chat)


def test_dto_names_exported() -> None:
    """成员选择、成员、消息和工作台占位相关 DTO 全部导出。"""
    for name in (
        "SelectionMode",
        "RoleMemberSelection",
        "MemberSelection",
        "ChatMember",
        "ChatMessage",
        "GroupChatTopic",
        "ProjectGroupChat",
        "ProjectPhase",
        "TeamRun",
        "TeamArtifactSummary",
        "TeamStatusSummary",
        "MemberStatusEntry",
        "ProjectGroupActivitySummary",
    ):
        assert getattr(group_chats, name) is not None, name


def test_business_errors_exported() -> None:
    """业务校验错误类型导出。"""
    assert group_chats.GroupChatCreationError is not None
    assert group_chats.AgentNotFoundError is not None
    assert group_chats.AgentRoleMismatchError is not None


def test_exports_do_not_include_test_helpers_or_privates() -> None:
    """导出面不含测试 helper 或下划线内部名称。"""
    assert "__all__" in vars(group_chats)
    for name in group_chats.__all__:
        assert not name.startswith("_")
    assert "build_chat_members" not in group_chats.__all__
    assert "build_team_run" not in group_chats.__all__
    assert "load_demo_package" not in group_chats.__all__


def test_exported_create_group_chat_is_module_level() -> None:
    """create_group_chat 来自 creation_service 模块，不是测试或临时对象。"""
    assert (
        group_chats.create_group_chat.__module__
        == "app.group_chats.creation_service"
    )


def test_import_does_not_load_fastapi_or_register_routes() -> None:
    """全新解释器中导入 `app.group_chats` 不引入 FastAPI / app.main，不注册路由。"""
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


def test_fresh_interpreter_import_succeeds_without_side_effects() -> None:
    """全新解释器中导入 `app.group_chats` 成功且不读取 demo package。"""
    code = (
        "import app.group_chats as g; "
        "assert callable(g.create_group_chat); "
        "assert g.CreateGroupChatRequest is not None; "
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
    """`app.group_chats` 可通过 importlib 导入。"""
    module = importlib.import_module("app.group_chats")
    assert module.__name__ == "app.group_chats"
