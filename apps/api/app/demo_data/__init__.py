"""Demo 数据模块：合成 Demo 数据包的加载、校验、对象构造与完整性保护。

内部模块边界（设计 §2.2）：

- 只服务静态数据包读取、校验与对象构造，不负责持久化、API 路由或 Agent 调度。
- 不访问网络、不访问数据库、不调用 LLM。
- 本入口暴露稳定内部导入面，调用方不依赖文件内部结构。

导入本模块不会读取 `package.json`，也不会导入 FastAPI app 或注册路由。
"""

from .integrity_guard import (
    DemoIntegrityError,
    validate_demo_object_integrity,
    validate_demo_package_integrity,
)
from .loader import load_demo_package
from .object_factory import (
    DemoObjectBundle,
    build_demo_objects,
    reset_demo_objects,
)
from .package_schema import DemoDataPackage

__all__ = [
    "DemoDataPackage",
    "DemoObjectBundle",
    "DemoIntegrityError",
    "load_demo_package",
    "build_demo_objects",
    "reset_demo_objects",
    "validate_demo_package_integrity",
    "validate_demo_object_integrity",
]
