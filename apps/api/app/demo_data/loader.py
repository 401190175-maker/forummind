"""静态 Demo 数据包 loader。

本模块从仓库固定的 demo_data 根目录读取静态数据包 `package.json`，
解析 JSON 并交给 `DemoDataPackage` 校验，返回已校验的数据包对象。

边界约定：

- 只读取 `DEMO_DATA_ROOT / <package_id> / package.json`，不接受任意路径，
  不扫描任意目录（设计 §8.5）。
- 不访问网络、不访问数据库、不调用 LLM（设计 §8.3）。
- 文件缺失 / JSON 解析失败 / schema 校验失败分别抛出明确的类型化异常
  （设计 §7.1），异常信息携带 package_id、期望文件路径与校验详情。
"""

import json
from pathlib import Path

from pydantic import ValidationError

from app.demo_data.package_schema import DemoDataPackage

# 本文件位于 apps/api/app/demo_data/loader.py：
# parents[0]=app/demo_data，parents[1]=app，parents[2]=api，
# parents[3]=apps，parents[4]=仓库根目录；demo_data 数据包目录固定在仓库根下。
DEMO_DATA_ROOT: Path = Path(__file__).resolve().parents[4] / "demo_data"


class DemoDataError(Exception):
    """Demo 数据包加载错误基类，全部 loader 异常统一继承。"""


class DemoPackageNotFoundError(DemoDataError):
    """数据包文件不存在（package_id 未知或文件缺失）。"""


class DemoPackageParseError(DemoDataError):
    """数据包 package.json JSON 解析失败。"""


class DemoPackageValidationError(DemoDataError):
    """数据包 schema 校验失败，同时保留原始 Pydantic ValidationError 供调用方检查。"""

    def __init__(self, message: str, validation_error: ValidationError) -> None:
        super().__init__(message)
        self.validation_error = validation_error


class DemoPackageInvalidIdError(DemoDataError):
    """package_id 不合法（含路径分隔符、`..` 或为空），在文件系统访问前直接拒绝。"""


def _is_invalid_package_id(package_id: str) -> bool:
    """package_id 含 `/`、`\\`、`..` 或为空白/空串时视为非法，禁止拼入文件路径。"""
    return (
        not package_id.strip()
        or "/" in package_id
        or "\\" in package_id
        or ".." in package_id
    )


def load_demo_package(package_id: str) -> DemoDataPackage:
    """从固定 demo_data 根目录读取并校验指定数据包。

    参数:
        package_id: 数据包标识，映射到 `DEMO_DATA_ROOT / package_id / package.json`。

    返回:
        通过 `DemoDataPackage` 校验的数据包对象。

    异常:
        DemoPackageInvalidIdError: package_id 不合法（路径穿越防护，不访问文件系统）。
        DemoPackageNotFoundError: 数据包文件不存在。
        DemoPackageParseError: package.json JSON 解析失败。
        DemoPackageValidationError: schema 校验失败（保留 Pydantic 校验信息）。
    """
    if _is_invalid_package_id(package_id):
        raise DemoPackageInvalidIdError(
            f"非法的 Demo 数据包 package_id: {package_id!r}"
            "（不允许包含路径分隔符 `/`、`\\` 或 `..`）"
        )

    package_path = DEMO_DATA_ROOT / package_id / "package.json"
    try:
        raw = package_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DemoPackageNotFoundError(
            f"Demo 数据包不存在: package_id={package_id!r}，期望路径: {package_path}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DemoPackageParseError(
            f"Demo 数据包 JSON 解析失败: {package_path}（{exc}）"
        ) from exc

    try:
        return DemoDataPackage.model_validate(data)
    except ValidationError as exc:
        raise DemoPackageValidationError(
            f"Demo 数据包 schema 校验失败: {package_path}（{exc}）",
            validation_error=exc,
        ) from exc
