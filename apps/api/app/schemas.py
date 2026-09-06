"""启动级响应模型。

仅包含健康检查与版本信息所需的字段，
不得包含 Project、Claim、Evidence、ResearchState 等科研业务字段。
"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    service: str
    environment: str


class VersionResponse(BaseModel):
    """服务版本信息响应。"""

    service: str
    version: str
    environment: str
