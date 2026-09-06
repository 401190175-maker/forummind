"""成员选择请求 DTO 测试（Task 2）。

覆盖：`SelectionMode` 枚举值域、`RoleMemberSelection` 字段约束
（existing 必须有非空 agent_ids；generate 必须有 count >= 1）、
非法 selection_mode 触发 Pydantic ValidationError，以及
schemas 模块不导入 FastAPI、不访问文件系统/数据库。
"""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.group_chats.schemas import (
    MemberSelection,
    RoleMemberSelection,
    SelectionMode,
)

# 测试文件位于 <repo>/apps/api/tests/group_chats/，仓库根为 parents[4]。
_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_selection_mode_values() -> None:
    """SelectionMode 只允许 existing 和 generate。"""
    assert {mode.value for mode in SelectionMode} == {"existing", "generate"}


def test_existing_mode_requires_agent_ids() -> None:
    """existing 模式提供非空 agent_ids 时校验通过。"""
    selection = RoleMemberSelection(
        selection_mode=SelectionMode.EXISTING,
        agent_ids=["agent-postdoc-001"],
    )
    assert selection.selection_mode is SelectionMode.EXISTING
    assert selection.agent_ids == ["agent-postdoc-001"]


def test_existing_mode_missing_agent_ids_fails() -> None:
    """existing 模式缺少 agent_ids 时校验失败。"""
    with pytest.raises(ValidationError):
        RoleMemberSelection(selection_mode=SelectionMode.EXISTING)


def test_existing_mode_empty_agent_ids_fails() -> None:
    """existing 模式 agent_ids 为空列表时校验失败。"""
    with pytest.raises(ValidationError):
        RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=[],
        )


def test_existing_mode_empty_string_agent_id_fails() -> None:
    """existing 模式 agent_id 为空白字符串时校验失败。"""
    with pytest.raises(ValidationError):
        RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=["   "],
        )


def test_generate_mode_requires_count() -> None:
    """generate 模式提供 count 时校验通过。"""
    selection = RoleMemberSelection(
        selection_mode=SelectionMode.GENERATE,
        count=1,
    )
    assert selection.selection_mode is SelectionMode.GENERATE
    assert selection.count == 1


def test_generate_mode_missing_count_fails() -> None:
    """generate 模式缺少 count 时校验失败。"""
    with pytest.raises(ValidationError):
        RoleMemberSelection(selection_mode=SelectionMode.GENERATE)


def test_generate_mode_zero_count_fails() -> None:
    """generate 模式 count 为 0 时校验失败。"""
    with pytest.raises(ValidationError):
        RoleMemberSelection(
            selection_mode=SelectionMode.GENERATE,
            count=0,
        )


def test_invalid_selection_mode_fails() -> None:
    """selection_mode 非法字符串触发 Pydantic ValidationError。"""
    with pytest.raises(ValidationError):
        RoleMemberSelection(
            selection_mode="unknown",
            agent_ids=["agent-postdoc-001"],
        )


def test_member_selection_has_three_role_keys() -> None:
    """MemberSelection 包含 postdoc / phd_student / master_student 三个角色键。"""
    selection = MemberSelection(
        postdoc=RoleMemberSelection(
            selection_mode=SelectionMode.EXISTING,
            agent_ids=["agent-postdoc-001"],
        ),
        phd_student=RoleMemberSelection(
            selection_mode=SelectionMode.GENERATE,
            count=1,
        ),
        master_student=RoleMemberSelection(
            selection_mode=SelectionMode.GENERATE,
            count=3,
        ),
    )
    assert selection.postdoc.agent_ids == ["agent-postdoc-001"]
    assert selection.phd_student.count == 1
    assert selection.master_student.count == 3


def test_schemas_import_has_no_fastapi_or_side_effects() -> None:
    """全新解释器中导入 `app.group_chats.schemas` 不引入 FastAPI，不做文件/数据库访问。

    注：导入会经父包 `app.group_chats` 间接引入 `app.demo_data` 模块
    （类型层依赖），但模块导入不读取 package.json；demo package
    读取副作用检查由 test_group_chats_exports.py 承担。
    """
    code = (
        "from app.group_chats.schemas import SelectionMode, RoleMemberSelection; "
        "import sys; "
        "assert 'fastapi' not in sys.modules; "
        "assert 'starlette' not in sys.modules; "
        "assert 'app.main' not in sys.modules; "
        "assert SelectionMode.EXISTING.value == 'existing'; "
        "assert RoleMemberSelection(selection_mode='generate', count=1) is not None; "
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
