"""创建课题组群聊服务（design §9、§10）。

职责：

- 把请求中的成员选择解析为群聊成员初始化对象（Task 8）。
- 使用 demo 数据包中的 synthetic `AgentProfile` 校验已有 Agent
  ID 是否存在且角色匹配（Task 9）。
- 构造课题组群聊初始化响应与工作台占位（Task 10、Task 11）。

边界约定：

- 服务不调用 LLM、不执行 Agent、不写正式 Memory、不访问网络；应用配置 SQLite 时保存课题组响应。
- 生成占位成员不伪造真实 `AgentProfile`，不调用任何 Agent 创建流程。
- 业务校验错误通过 `GroupChatCreationError` 子类表达，可映射为 422。
"""

import time
import uuid
import hashlib

from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import build_agent_profiles, build_demo_objects
from app.demo_data.package_schema import DemoDataPackage
from app.agents import service as agents_service
from app.domain.schemas import (
    AgentProfile,
    AgentRole,
    DataSpace,
    ObjectReference,
    ObjectType,
    Task,
)
from app.group_chats.schemas import (
    ChatMember,
    ChatMessage,
    CreateGroupChatRequest,
    CreateGroupChatResponse,
    GenerateProfile,
    GroupChatTopic,
    MemberSelection,
    MemberStatusEntry,
    ProjectGroupActivitySummary,
    ProjectGroupChat,
    SelectionMode,
    TeamArtifactSummary,
    TeamRun,
    TeamStatusSummary,
)
from app.storage.repositories import GroupChatRepository, MessageRepository
from app.meeting.scheduler import schedule_service
from app.storage.repositories import (
    ArtifactRepository,
    ClarificationRepository,
    FormalTaskRepository,
    MeetingRepository,
    RunRepository,
)
from app.storage.sqlite_store import SQLiteStore


DEFAULT_LIVE_RESEARCH_TOOLS = (
    "knowledge.search",
    "experiment.analyze",
    "literature.search",
)


class GroupChatCreationError(Exception):
    """创建课题组业务错误基类（可映射为 422）。"""


class AgentNotFoundError(GroupChatCreationError):
    """`existing` 模式引用了 demo 数据包中不存在的 Agent id。"""


class AgentRoleMismatchError(GroupChatCreationError):
    """`existing` 模式引用的 Agent 角色与所选角色键不匹配。"""


class DuplicateAgentReferenceError(GroupChatCreationError):
    """A group chat cannot attach the same Agent more than once."""


class GeneratedMemberConfigurationError(GroupChatCreationError):
    """A generated member cannot be confirmed with the supplied profile."""


_created_group_chats: dict[str, CreateGroupChatResponse] = {}
_persistence_store: SQLiteStore | None = None
_group_chat_repository: GroupChatRepository | None = None


def configure_persistence(store: SQLiteStore | None) -> None:
    """Configure optional durable storage for application-level group chats."""
    global _persistence_store, _group_chat_repository
    _persistence_store = store
    _group_chat_repository = GroupChatRepository(store) if store else None


def get_created_group_chat(group_chat_id: str) -> CreateGroupChatResponse | None:
    """Return a group chat from SQLite or the process-local fallback."""
    if _group_chat_repository is not None:
        stored = _group_chat_repository.get(group_chat_id)
        if stored is None:
            return None
        recovered = CreateGroupChatResponse.model_validate(stored["payload"])
        _created_group_chats[group_chat_id] = recovered
        return recovered
    return _created_group_chats.get(group_chat_id)


def list_created_group_chats(query: str | None = None) -> list[CreateGroupChatResponse]:
    """Return created group chats, optionally filtered by visible card text."""
    if _group_chat_repository is None:
        records = list(_created_group_chats.values())
    else:
        records = [
            CreateGroupChatResponse.model_validate(stored["payload"])
            for stored in _group_chat_repository.list()
        ]
        _created_group_chats.update(
            {record.group_chat.id: record for record in records}
        )

    needle = query.strip().casefold() if isinstance(query, str) else ""
    if not needle:
        return records
    return [record for record in records if needle in _group_chat_search_text(record)]


def _group_chat_search_text(record: CreateGroupChatResponse) -> str:
    """Build the searchable text shown by the group-card and member summaries."""
    values: list[str] = [
        record.group_chat.topic_name,
        record.group_chat.topic_summary,
        record.group_chat.data_space.value,
        record.project_phase.value,
        record.persistence,
        record.agent_automation,
    ]
    for member in record.members:
        values.extend([member.display_name, member.role.value, member.status])
        if member.generate_profile is not None:
            profile = member.generate_profile
            values.extend(
                value
                for value in (
                    profile.display_name,
                    profile.primary_ability,
                    profile.description,
                    profile.specialty_domain,
                    profile.knowledge_base_coverage,
                    profile.forbidden_actions,
                )
                if value
            )
            values.extend(profile.secondary_abilities)
            values.extend(profile.general_research_abilities)
            values.extend(profile.allowed_tools)
    return " ".join(values).casefold()


def reset_created_group_chats() -> None:
    """Clear process and configured persistent group-chat state."""
    _created_group_chats.clear()
    if _group_chat_repository is not None:
        _group_chat_repository.delete_all()


def _persist_response(response: CreateGroupChatResponse) -> None:
    if _persistence_store is None or _group_chat_repository is None:
        return
    message_repository = MessageRepository(_persistence_store)
    now = time.time()
    with _persistence_store.transaction():
        _group_chat_repository.save(
            {
                "group_chat_id": response.group_chat.id,
                "data_space": response.group_chat.data_space.value,
                "payload": response.model_dump(mode="json"),
                "created_at": now,
                "updated_at": now,
            }
        )
        # Initial messages are immutable; only insert them when this is the
        # first persistence of a group to keep updates idempotent.
        if not message_repository.list(response.group_chat.id):
            for index, message in enumerate(response.initial_messages):
                message_repository.append(
                    {
                        "message_id": message.id,
                        "group_chat_id": response.group_chat.id,
                        "sender_type": message.sender_type,
                        "sender_id": "postdoc" if message.sender_type == "agent" else None,
                        "content": message.content,
                        "mention": None,
                        "task_id": None,
                        "attachment_ids": [],
                        "kind": "text",
                        "payload": {},
                        "reply_to_message_id": None,
                        "data_space": response.group_chat.data_space.value,
                        "created_at": now + index * 0.000001,
                    }
                )


# 成员选择角色键 -> 领域 AgentRole。
_ROLE_KEY_TO_AGENT_ROLE: dict[str, AgentRole] = {
    "postdoc": AgentRole.POSTDOC,
    "phd_student": AgentRole.PHD_STUDENT,
    "master_student": AgentRole.MASTER_STUDENT,
}

# 成员选择角色键 -> 中文角色标签（用于生成占位展示名）。
_ROLE_LABELS: dict[str, str] = {
    "postdoc": "博士后",
    "phd_student": "博士",
    "master_student": "硕士",
}


def make_agent_profile_ref(package: DemoDataPackage, agent_id: str) -> ObjectReference:
    """构造指向 demo synthetic `AgentProfile` 的确定性引用。

    ID 方案与 demo 模块一致（`package_id@version:object_type:local_key`），
    保证同一数据包版本多次构造得到同一引用。
    """
    if any(profile.local_key == agent_id for profile in package.agent_profiles):
        return _make_object_ref(package, ObjectType.AGENT_PROFILE, agent_id)
    return ObjectReference(
        object_type=ObjectType.AGENT_PROFILE,
        object_id=f"agent:{agent_id}",
    )


def _make_object_ref(
    package: DemoDataPackage, object_type: ObjectType, local_key: str
) -> ObjectReference:
    """按 demo 模块确定性 ID 方案构造对象引用（design §4.3 同款约定）。"""
    return ObjectReference(
        object_type=object_type,
        object_id=(
            f"{package.package_id}@{package.version}"
            f":{object_type.value}:{local_key}"
        ),
    )


def _agent_index(package: DemoDataPackage) -> dict[str, AgentProfile]:
    """构造 package 级 Agent 索引：local_key -> 领域 AgentProfile。

    package 级画像与领域对象顺序一一对应，zip 后按 local_key 建索引。
    """
    domain_profiles = build_agent_profiles(package)
    return {
        pkg_profile.local_key: domain_profile
        for pkg_profile, domain_profile in zip(
            package.agent_profiles, domain_profiles
        )
    }


def _resolve_existing_agent(
    package: DemoDataPackage,
    agent_index: dict[str, AgentProfile],
    role_key: str,
    agent_id: str,
) -> AgentProfile:
    """Resolve an existing Agent from the persisted AgentService index."""
    persisted = agents_service.get_agent_record(agent_id)
    if persisted is None:
        raise AgentNotFoundError(
            f"Agent id 不存在: {agent_id!r}（服务端 Agent 索引中不可用）"
        )
    if not persisted.get("enabled", False):
        raise AgentNotFoundError(f"Agent 已停用，不能加入课题组: {agent_id!r}")
    profile = AgentProfile.model_validate(persisted["profile"])
    expected_role = _ROLE_KEY_TO_AGENT_ROLE[role_key]
    if profile.role is not expected_role:
        raise AgentRoleMismatchError(
            f"Agent 角色不匹配: agent_id={agent_id!r} 是 {profile.role.value}，"
            f"但成员选择角色键 {role_key!r} 需要 {expected_role.value}"
        )
    return profile


def validate_existing_agents(
    package: DemoDataPackage,
    member_selection: MemberSelection,
) -> None:
    """校验成员选择中全部 `existing` Agent 引用存在且角色匹配（design §9）。

    只读取 demo package 与内存对象，不写数据库、不访问网络、
    不调用 Agent 创建流程；`demo_package_id` 加载错误由
    demo loader 的明确异常原样透传。
    """
    seen_agent_ids: set[str] = set()
    for role_key, selection in (
        ("postdoc", member_selection.postdoc),
        ("phd_student", member_selection.phd_student),
        ("master_student", member_selection.master_student),
    ):
        if selection.selection_mode is SelectionMode.EXISTING:
            for agent_id in selection.agent_ids or []:
                if agent_id in seen_agent_ids:
                    raise DuplicateAgentReferenceError(
                        f"Agent 不能重复加入课题组: {agent_id!r}"
                    )
                seen_agent_ids.add(agent_id)
                _resolve_existing_agent(package, {}, role_key, agent_id)


def build_chat_members(
    group_chat_id: str,
    member_selection: MemberSelection,
    package: DemoDataPackage,
) -> list[ChatMember]:
    """把成员选择解析为群聊成员列表（design §8）。

    - `existing` 成员状态为 `active`，携带指向 demo `AgentProfile` 的引用。
    - `generate` 成员状态为 `pending_generation`，只创建待生成占位，
      不伪造真实 `AgentProfile`，不调用任何 Agent 创建流程。
    - 成员 id 为请求级稳定 id（`<group_chat_id>:<role_key>:<agent_id|gen-N>`）。
    """
    members: list[ChatMember] = []

    for role_key, selection in (
        ("postdoc", member_selection.postdoc),
        ("phd_student", member_selection.phd_student),
        ("master_student", member_selection.master_student),
    ):
        if selection.selection_mode is SelectionMode.EXISTING:
            for agent_id in selection.agent_ids or []:
                profile = _resolve_existing_agent(package, {}, role_key, agent_id)
                members.append(
                    ChatMember(
                        id=f"{group_chat_id}:{role_key}:{agent_id}",
                        group_chat_id=group_chat_id,
                        role=_ROLE_KEY_TO_AGENT_ROLE[role_key],
                        selection_mode=SelectionMode.EXISTING,
                        agent_profile_ref=make_agent_profile_ref(package, agent_id),
                        display_name=profile.name,
                        status="active",
                    )
                )
        else:
            profiles = selection.generate_profiles or []
            for index in range(1, (selection.count or 0) + 1):
                profile = profiles[index - 1] if index - 1 < len(profiles) else None
                members.append(
                    ChatMember(
                        id=f"{group_chat_id}:{role_key}:gen-{index}",
                        group_chat_id=group_chat_id,
                        role=_ROLE_KEY_TO_AGENT_ROLE[role_key],
                        selection_mode=SelectionMode.GENERATE,
                        display_name=(
                            profile.display_name
                            if profile and profile.display_name
                            else f"待生成{_ROLE_LABELS[role_key]} Agent {index}"
                        ),
                        status="pending_generation",
                        generate_profile=profile,
                    )
                )

    return members


def build_team_run(group_chat_id: str) -> TeamRun:
    """团队运行入口占位（design §7）：固定未启动、自动化关闭。"""
    return TeamRun(
        id=f"{group_chat_id}:team-run",
        group_chat_id=group_chat_id,
    )


def build_artifact_summary(
    group_chat_id: str, members: list[ChatMember]
) -> TeamArtifactSummary:
    """产物摘要占位（design §7）：每个 Agent 一个文件夹 + 例会记录，无真实文件。"""
    folders = [member.id for member in members] + ["例会记录"]
    return TeamArtifactSummary(
        group_chat_id=group_chat_id,
        folders=folders,
        naming_rule="日期 + 任务名 + Agent 名",
    )


def _member_status_overview(members: list[ChatMember]) -> str:
    """成员状态概览文本：已有 Agent 空闲数量与待生成数量。"""
    active_count = sum(1 for member in members if member.status == "active")
    pending_count = sum(
        1 for member in members if member.status == "pending_generation"
    )
    return (
        f"{active_count} 名成员空闲（绿灯），"
        f"{pending_count} 名成员待生成（待配置）"
    )


def build_team_status(
    group_chat_id: str, members: list[ChatMember]
) -> TeamStatusSummary:
    """成员状态摘要占位（design §7）：已有 Agent 默认 idle，生成占位保持待生成。"""
    entries = [
        MemberStatusEntry(
            member_id=member.id,
            display_name=member.display_name,
            status="idle"
            if member.status == "active"
            else "pending_generation",
        )
        for member in members
    ]
    return TeamStatusSummary(
        group_chat_id=group_chat_id,
        member_statuses=entries,
    )


def build_activity_summary(
    group_chat_id: str, members: list[ChatMember]
) -> ProjectGroupActivitySummary:
    """课题组动态占位（design §7）：默认无新交付、无新讨论记录。"""
    return ProjectGroupActivitySummary(
        group_chat_id=group_chat_id,
        member_status_overview=_member_status_overview(members),
    )


def build_initial_messages(
    group_chat_id: str, request: CreateGroupChatRequest
) -> list[ChatMessage]:
    """Build initial chat messages without claiming real evidence exists."""
    if request.data_space is not DataSpace.SYNTHETIC:
        return [
            ChatMessage(
                id=f"{group_chat_id}:msg-1",
                group_chat_id=group_chat_id,
                sender_type="agent",
                content=(
                    f"我是本课题的博士后。已创建“{request.topic_name}”，"
                    f"研究方向是：{request.topic_summary}。"
                ),
            ),
            ChatMessage(
                id=f"{group_chat_id}:msg-2",
                group_chat_id=group_chat_id,
                sender_type="agent",
                content=(
                    "请先上传需要分析的科研资料。资料解析完成后，"
                    "可以 @ 成员分配研究任务，或安排下一次组会。"
                ),
            ),
        ]
    return [
        ChatMessage(
            id=f"{group_chat_id}:msg-1",
            group_chat_id=group_chat_id,
            content=(
                f"课题组已创建：{request.topic_name}。"
                f"课题概述：{request.topic_summary}。"
            ),
        ),
        ChatMessage(
            id=f"{group_chat_id}:msg-2",
            group_chat_id=group_chat_id,
            content=(
                "本课题组为合成演示初始化结果：数据空间 synthetic，"
                "已保存到本地 SQLite，Agent 自动化未启用（disabled）。"
            ),
        ),
    ]


def _build_real_chat_members(
    group_chat_id: str, member_selection: MemberSelection
) -> list[ChatMember]:
    """Build real-workspace members without loading the synthetic package."""
    members: list[ChatMember] = []
    for role_key, selection in (
        ("postdoc", member_selection.postdoc),
        ("phd_student", member_selection.phd_student),
        ("master_student", member_selection.master_student),
    ):
        if selection.selection_mode is SelectionMode.EXISTING:
            for agent_id in selection.agent_ids or []:
                profile_record = agents_service.get_agent_record(agent_id)
                if profile_record is None:
                    raise AgentNotFoundError(
                        f"Agent id 不存在: {agent_id!r}（服务端 Agent 索引中不可用）"
                    )
                if not profile_record.get("enabled", False):
                    raise AgentNotFoundError(f"Agent 已停用，不能加入课题组: {agent_id!r}")
                profile = AgentProfile.model_validate(profile_record["profile"])
                expected_role = _ROLE_KEY_TO_AGENT_ROLE[role_key]
                if profile.role is not expected_role:
                    raise AgentRoleMismatchError(
                        f"Agent 角色不匹配: agent_id={agent_id!r} 是 {profile.role.value}，"
                        f"但成员选择角色键 {role_key!r} 需要 {expected_role.value}"
                    )
                members.append(
                    ChatMember(
                        id=f"{group_chat_id}:{role_key}:{agent_id}",
                        group_chat_id=group_chat_id,
                        role=expected_role,
                        selection_mode=SelectionMode.EXISTING,
                        agent_profile_ref=ObjectReference(
                            object_type=ObjectType.AGENT_PROFILE,
                            object_id=f"agent:{agent_id}",
                        ),
                        display_name=profile.name,
                        status="active",
                    )
                )
            continue
        profiles = selection.generate_profiles or []
        for index in range(1, (selection.count or 0) + 1):
            profile = profiles[index - 1] if index - 1 < len(profiles) else None
            members.append(
                ChatMember(
                    id=f"{group_chat_id}:{role_key}:gen-{index}",
                    group_chat_id=group_chat_id,
                    role=_ROLE_KEY_TO_AGENT_ROLE[role_key],
                    selection_mode=SelectionMode.GENERATE,
                    display_name=(
                        profile.display_name
                        if profile and profile.display_name
                        else f"待生成{_ROLE_LABELS[role_key]} Agent {index}"
                    ),
                    status="pending_generation",
                    generate_profile=profile,
                )
            )
    return members


def _create_real_group_chat(request: CreateGroupChatRequest) -> CreateGroupChatResponse:
    """Create an empty real workspace with no demo-derived research objects."""
    group_chat_id = f"gc-{uuid.uuid4().hex[:12]}"
    members = _build_real_chat_members(group_chat_id, request.member_selection)
    team_run = build_team_run(group_chat_id)
    artifact_summary = build_artifact_summary(group_chat_id, members)
    team_status = build_team_status(group_chat_id, members)
    activity_summary = build_activity_summary(group_chat_id, members)
    group_chat = ProjectGroupChat(
        id=group_chat_id,
        topic_name=request.topic_name,
        topic_summary=request.topic_summary,
        data_space=request.data_space,
        member_refs=[
            member.agent_profile_ref
            for member in members
            if member.agent_profile_ref is not None
        ],
        project_ref=None,
        team_run_ref=None,
        artifact_summary_ref=None,
        activity_summary_ref=None,
    )
    response = CreateGroupChatResponse(
        group_chat=group_chat,
        topic=GroupChatTopic(
            topic_name=request.topic_name,
            topic_summary=request.topic_summary,
        ),
        members=members,
        initial_messages=build_initial_messages(group_chat_id, request),
        project=None,
        research_question=None,
        research_state=None,
        placeholder_tasks=[],
        team_run=team_run,
        artifact_summary=artifact_summary,
        team_status=team_status,
        activity_summary=activity_summary,
        warnings=[
            f"当前为 {request.data_space.value} 真实工作区，未加载 synthetic demo 数据。",
            "请先上传并完成解析的科研资料；Agent 只能通过授权检索工具读取资料。",
        ],
    )
    _persist_response(response)
    _created_group_chats[group_chat_id] = response
    return response


def create_group_chat(request: CreateGroupChatRequest) -> CreateGroupChatResponse:
    """创建请求级课题组群聊初始化响应（design §6、§10）。

    流程：加载 demo 数据包 -> 校验已有 Agent -> 构造成员 ->
    关联 synthetic 科研对象 -> 填充工作台占位 -> 持久化快照。
    不调用 LLM、不执行 Agent、不写 Memory。
    """
    if request.data_space is not DataSpace.SYNTHETIC:
        return _create_real_group_chat(request)

    package = load_demo_package(request.demo_package_id)
    validate_existing_agents(package, request.member_selection)

    bundle = build_demo_objects(package)
    group_chat_id = f"gc-{uuid.uuid4().hex[:12]}"

    members = build_chat_members(group_chat_id, request.member_selection, package)
    team_run = build_team_run(group_chat_id)
    artifact_summary = build_artifact_summary(group_chat_id, members)
    team_status = build_team_status(group_chat_id, members)
    activity_summary = build_activity_summary(group_chat_id, members)

    project_ref = _make_object_ref(package, ObjectType.PROJECT, "project")
    question_ref = _make_object_ref(
        package, ObjectType.RESEARCH_QUESTION, "research_question"
    )
    state_ref = _make_object_ref(
        package, ObjectType.RESEARCH_STATE, "research_state"
    )

    group_chat = ProjectGroupChat(
        id=group_chat_id,
        topic_name=request.topic_name,
        topic_summary=request.topic_summary,
        member_refs=[
            member.agent_profile_ref
            for member in members
            if member.agent_profile_ref is not None
        ],
        project_ref=project_ref,
        team_run_ref=None,
        artifact_summary_ref=None,
        activity_summary_ref=None,
    )

    topic = GroupChatTopic(
        topic_name=request.topic_name,
        topic_summary=request.topic_summary,
        project_ref=project_ref,
        research_question_ref=question_ref,
        research_state_ref=state_ref,
    )

    placeholder_tasks: list[Task] = (
        list(bundle.tasks) if request.create_placeholder_tasks else []
    )

    initial_messages = build_initial_messages(group_chat_id, request)
    response = CreateGroupChatResponse(
        group_chat=group_chat,
        topic=topic,
        members=members,
        initial_messages=initial_messages,
        project=bundle.project,
        research_question=bundle.research_question,
        research_state=bundle.research_state,
        placeholder_tasks=placeholder_tasks,
        team_run=team_run,
        artifact_summary=artifact_summary,
        team_status=team_status,
        activity_summary=activity_summary,
        warnings=[
            "当前为合成演示初始化结果（synthetic），已保存到本地 SQLite，"
            "Agent 自动化未启用（disabled）。",
            "generate 成员为待生成占位，未执行真实 Agent 创建；"
            "团队产物与运行状态均为占位，未创建真实文件。",
        ],
    )
    _persist_response(response)
    _created_group_chats[group_chat_id] = response
    return response


def delete_group_chat(group_chat_id: str) -> bool:
    """Delete a group and all dependent demo/live records atomically."""
    if _group_chat_repository is None or _persistence_store is None:
        existed = group_chat_id in _created_group_chats
        _created_group_chats.pop(group_chat_id, None)
        schedule_service.delete_for_group(group_chat_id)
        return existed

    message_repository = MessageRepository(_persistence_store)
    clarification_repository = ClarificationRepository(_persistence_store)
    formal_task_repository = FormalTaskRepository(_persistence_store)
    run_repository = RunRepository(_persistence_store)
    meeting_repository = MeetingRepository(_persistence_store)
    artifact_repository = ArtifactRepository(_persistence_store)
    with _persistence_store.transaction():
        deleted = _group_chat_repository.delete(group_chat_id)
        if not deleted:
            return False
        message_repository.delete_for_group(group_chat_id)
        clarification_repository.delete_for_group(group_chat_id)
        formal_task_repository.delete_for_group(group_chat_id)
        meeting_repository.delete_for_group(group_chat_id)
        artifact_repository.delete_for_group(group_chat_id)
        run_repository.delete_for_group(group_chat_id)
    # The API RunStore may already have hydrated snapshots in memory; clear
    # those only after the durable transaction commits successfully.
    from app.api import runs as runs_api

    runs_api.run_store.delete_for_group(group_chat_id)
    schedule_service.delete_for_group(group_chat_id)
    _created_group_chats.pop(group_chat_id, None)
    return True


def configure_generated_member(
    group_chat_id: str, member_id: str, configuration: GenerateProfile
) -> CreateGroupChatResponse:
    """Create and attach a real Agent only after explicit user confirmation."""
    response = get_created_group_chat(group_chat_id)
    if response is None:
        raise GroupChatCreationError(f"课题组不存在: {group_chat_id}")
    member = next((item for item in response.members if item.id == member_id), None)
    if member is None:
        raise GroupChatCreationError(f"成员不存在: {member_id}")
    if member.status == "active":
        if member.agent_profile_ref is None:
            raise GeneratedMemberConfigurationError("成员已激活但缺少 Agent 引用")
        return response

    prior = member.generate_profile.model_dump(mode="json") if member.generate_profile else {}
    supplied = configuration.model_dump(mode="json")
    merged = {**prior, **{key: value for key, value in supplied.items() if value is not None}}
    display_name = str(merged.get("display_name") or member.display_name).strip()
    primary_ability = str(merged.get("primary_ability") or "独立科研分析").strip()
    if not display_name or display_name.startswith("待生成"):
        raise GeneratedMemberConfigurationError("请先填写 Agent 名称")
    if not primary_ability:
        raise GeneratedMemberConfigurationError("请先填写 Agent 主能力")
    group_space = response.group_chat.data_space
    if group_space not in {DataSpace.REAL, DataSpace.DESENSITIZED_REAL}:
        raise GeneratedMemberConfigurationError(
            "生成成员只能加入真实科研课题组"
        )
    stable_suffix = hashlib.sha256(member.id.encode("utf-8")).hexdigest()[:16]
    agent_id = f"agent-generated-{stable_suffix}"
    requested_tools = [
        str(item).strip() for item in (merged.get("allowed_tools") or [])
        if str(item).strip()
    ]
    allowed_tools = list(dict.fromkeys(
        item for item in requested_tools if item in DEFAULT_LIVE_RESEARCH_TOOLS
    ))
    if not allowed_tools:
        allowed_tools = (
            ["knowledge.search"]
            if requested_tools
            else list(DEFAULT_LIVE_RESEARCH_TOOLS)
        )
    try:
        profile = AgentProfile(
            agent_id=agent_id,
            name=display_name,
            role=member.role,
            description=merged.get("description"),
            primary_ability=primary_ability,
            secondary_abilities=list(merged.get("secondary_abilities") or []),
            general_research_abilities=list(merged.get("general_research_abilities") or []),
            allowed_data_spaces=[group_space],
            allowed_tools=allowed_tools,
            forbidden_actions=merged.get("forbidden_actions"),
            specialty_domain=merged.get("specialty_domain"),
            knowledge_base_coverage=merged.get("knowledge_base_coverage"),
        )
    except Exception as exc:
        raise GeneratedMemberConfigurationError(f"生成 Agent 配置无效: {exc}") from exc
    existing_agent = agents_service.get_agent_record(agent_id)
    if existing_agent is None:
        try:
            agents_service.create_agent(profile)
        except Exception as exc:
            raise GeneratedMemberConfigurationError(
                f"Agent 创建失败，成员仍保持待配置: {exc}"
            ) from exc
    elif not existing_agent.get("enabled", False):
        raise GeneratedMemberConfigurationError("关联的 Agent 已停用，不能激活成员")

    agent_ref = ObjectReference(
        object_type=ObjectType.AGENT_PROFILE,
        object_id=f"agent:{agent_id}",
    )
    members = [
        item.model_copy(
            update={
                "selection_mode": SelectionMode.EXISTING,
                "agent_profile_ref": agent_ref,
                "display_name": profile.name,
                "status": "active",
                "generate_profile": None,
                "configuration_version": "v1",
            }
        )
        if item.id == member_id
        else item
        for item in response.members
    ]
    group_chat = response.group_chat.model_copy(
        update={
            "member_refs": [
                *(response.group_chat.member_refs or []),
                agent_ref,
            ]
        }
    )
    updated = response.model_copy(
        update={
            "group_chat": group_chat,
            "members": members,
            "artifact_summary": build_artifact_summary(group_chat_id, members),
            "team_status": build_team_status(group_chat_id, members),
            "activity_summary": build_activity_summary(group_chat_id, members),
        }
    )
    _persist_response(updated)
    _created_group_chats[group_chat_id] = updated
    return updated
