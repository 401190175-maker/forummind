"""课题组群聊业务包：HTTP DTO 与创建服务。

本包只承载 DTO（schemas.py）与创建服务（creation_service.py）。
创建服务在应用配置 SQLite 时保存课题组，不执行 Agent、不调用 LLM、不写正式 Memory。
本入口暴露稳定内部导入面，调用方不依赖文件内部结构；

导入本模块不会注册 FastAPI 路由、不会读取 demo package 文件、
不会访问网络或数据库（demo 模块仅在类型层被引用）。
"""

from .creation_service import (
    AgentNotFoundError,
    AgentRoleMismatchError,
    DuplicateAgentReferenceError,
    GeneratedMemberConfigurationError,
    GroupChatCreationError,
    create_group_chat,
    configure_generated_member,
    delete_group_chat,
    get_created_group_chat,
    reset_created_group_chats,
)
from .schemas import (
    ChatMember,
    ChatMessage,
    CreateGroupChatRequest,
    CreateGroupChatResponse,
    GroupChatTopic,
    MemberSelection,
    MemberStatusEntry,
    ProjectGroupActivitySummary,
    ProjectGroupChat,
    ProjectPhase,
    RoleMemberSelection,
    SelectionMode,
    TeamArtifactSummary,
    TeamRun,
    TeamStatusSummary,
)

__all__ = [
    # 请求 DTO
    "CreateGroupChatRequest",
    "MemberSelection",
    "RoleMemberSelection",
    "SelectionMode",
    # 响应 DTO
    "CreateGroupChatResponse",
    "ProjectGroupChat",
    "GroupChatTopic",
    "ChatMember",
    "ChatMessage",
    "ProjectPhase",
    "TeamRun",
    "TeamArtifactSummary",
    "TeamStatusSummary",
    "MemberStatusEntry",
    "ProjectGroupActivitySummary",
    # 创建服务与业务错误
    "create_group_chat",
    "configure_generated_member",
    "delete_group_chat",
    "get_created_group_chat",
    "reset_created_group_chats",
    "GroupChatCreationError",
    "AgentNotFoundError",
    "AgentRoleMismatchError",
    "DuplicateAgentReferenceError",
    "GeneratedMemberConfigurationError",
]
