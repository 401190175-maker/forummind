"""课题组群聊 API router（design §4、§12）。

暴露 `POST/GET /group-chats` 与 `GET /group-chats/{id}`：接收创建请求、
读取服务端课题组记录，并把业务校验错误转换为 422 响应。路由函数不
承载成员解析、demo 对象构造或业务拼装逻辑。
"""

from fastapi import APIRouter, Header, HTTPException, Query

from app.demo_data.loader import (
    DemoPackageInvalidIdError,
    DemoPackageNotFoundError,
    DemoPackageParseError,
    DemoPackageValidationError,
)
from app.group_chats.creation_service import (
    GroupChatCreationError,
    configure_generated_member,
    delete_group_chat,
    create_group_chat,
    get_created_group_chat,
    list_created_group_chats,
)
from app.group_chats.messages import (
    ClarificationClosedError,
    ClarificationProtocolError,
    ClarificationNotFoundError,
    ClarificationRuntimeError,
    GroupChatMemberNotFoundError,
    GroupChatMissingPhDError,
    add_user_message,
    append_chat_message,
    answer_task_clarification,
    create_formal_task,
    create_task_clarification,
    list_clarifications,
    list_messages,
)
from app.group_chats.schemas import (
    ChatMessageRecord,
    CreateGroupChatRequest,
    CreateGroupChatResponse,
    CreateMessageRequest,
    TaskClarificationAnswerRequest,
    TaskClarificationRequest,
    TaskClarificationResponse,
    FormalTaskContext,
    GenerateProfile,
)
from app.auth.dependencies import (
    auth_required,
    get_current_user,
    require_group_access,
    service_auth,
)
from app.permissions.policy import authorize_group_access
from app.meeting.scheduler import (
    MeetingScheduleRequest,
    MeetingScheduleResponse,
    schedule_service,
)

router = APIRouter(prefix="/group-chats", tags=["group-chats"])


@router.post("", response_model=CreateGroupChatResponse)
def create_group_chat_route(
    request: CreateGroupChatRequest,
    authorization: str | None = Header(default=None),
) -> CreateGroupChatResponse:
    """创建课题组并初始化课题组群聊（design §4）。

    错误映射（design §11）：成员/结构校验错误与非法或不存在的
    demo 数据包 id -> 422；静态数据包解析或 schema 配置错误 -> 500。
    """
    try:
        current_user = get_current_user(authorization)
        response = create_group_chat(request)
        if auth_required():
            auth_service = service_auth()
            if auth_service is None:
                raise HTTPException(status_code=503, detail="authentication service is unavailable")
            auth_service.add_membership(
                current_user.user_id, response.group_chat.id, "owner"
            )
        return response
    except GroupChatCreationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DemoPackageInvalidIdError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DemoPackageNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DemoPackageParseError, DemoPackageValidationError) as exc:
        raise HTTPException(
            status_code=500, detail="demo 数据包配置错误，请检查静态数据包"
        ) from exc


@router.get("", response_model=list[CreateGroupChatResponse])
def list_group_chats_route(
    query: str | None = Query(default=None, max_length=200),
    authorization: str | None = Header(default=None),
) -> list[CreateGroupChatResponse]:
    """Return all persisted group-chat creation responses."""
    records = list_created_group_chats(query)
    if not auth_required():
        return records
    user = get_current_user(authorization)
    return [
        record
        for record in records
        if authorize_group_access(user, record.group_chat.id, "read").allowed
    ]


@router.get("/{group_chat_id}", response_model=CreateGroupChatResponse)
def get_group_chat_route(
    group_chat_id: str,
    authorization: str | None = Header(default=None),
) -> CreateGroupChatResponse:
    """Return a group-chat creation response by ID."""
    _require_group_chat(group_chat_id, authorization)
    record = get_created_group_chat(group_chat_id)
    if record is None:
        raise HTTPException(status_code=404, detail="课题组不存在")
    return record


@router.delete("/{group_chat_id}")
def delete_group_chat_route(
    group_chat_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    """Delete a group and its dependent messages, runs, events and artifacts."""
    _require_group_chat(group_chat_id, authorization, action="admin")
    if not delete_group_chat(group_chat_id):
        raise HTTPException(status_code=404, detail="课题组不存在")
    return {"deleted": True, "group_chat_id": group_chat_id}


@router.get(
    "/{group_chat_id}/meeting-schedule",
    response_model=MeetingScheduleResponse | None,
)
def get_meeting_schedule_route(
    group_chat_id: str,
    authorization: str | None = Header(default=None),
) -> MeetingScheduleResponse | None:
    """Read the server-owned next meeting schedule for a group."""
    _require_group_chat(group_chat_id, authorization)
    return schedule_service.get(group_chat_id)


@router.put(
    "/{group_chat_id}/meeting-schedule",
    response_model=MeetingScheduleResponse,
)
def save_meeting_schedule_route(
    group_chat_id: str,
    request: MeetingScheduleRequest,
    authorization: str | None = Header(default=None),
) -> MeetingScheduleResponse:
    """Persist the next meeting time; the API process scheduler consumes it."""
    _require_group_chat(group_chat_id, authorization, action="write")
    response = schedule_service.save(group_chat_id, request.next_meeting_at)
    append_chat_message(
        group_chat_id,
        sender_type="agent",
        sender_id="postdoc",
        content="已安排下一次组会。",
        kind="meeting_schedule",
        payload={"next_meeting_at": response.next_meeting_at.isoformat()},
    )
    return response


@router.patch(
    "/{group_chat_id}/members/{member_id}/configuration",
    response_model=CreateGroupChatResponse,
)
def configure_generated_member_route(
    group_chat_id: str,
    member_id: str,
    configuration: GenerateProfile,
    authorization: str | None = Header(default=None),
) -> CreateGroupChatResponse:
    """Confirm a generated member and attach its real persisted Agent."""
    _require_group_chat(group_chat_id, authorization, action="admin")
    try:
        return configure_generated_member(group_chat_id, member_id, configuration)
    except GroupChatCreationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _require_group_chat(
    group_chat_id: str,
    authorization: str | None = None,
    *,
    action: str = "read",
) -> None:
    """demo-safe 路由的课题组存在性校验（design §7.2：不存在 -> 404）。"""
    require_group_access(group_chat_id, authorization, action)
    if get_created_group_chat(group_chat_id) is None:
        raise HTTPException(status_code=404, detail="课题组不存在")


@router.post("/{group_chat_id}/messages", response_model=ChatMessageRecord)
def create_message(
    group_chat_id: str,
    request: CreateMessageRequest,
    authorization: str | None = Header(default=None),
) -> ChatMessageRecord:
    """保存 demo 用户消息（design §5.2）。

    写入 SQLite（未配置时使用进程内 demo store），不启动 run、不写正式 Memory。
    """
    _require_group_chat(group_chat_id, authorization, action="write")
    return add_user_message(group_chat_id, request)


@router.get("/{group_chat_id}/messages", response_model=list[ChatMessageRecord])
def get_messages(
    group_chat_id: str,
    authorization: str | None = Header(default=None),
) -> list[ChatMessageRecord]:
    """按创建顺序返回该群聊的 demo 消息（design §5.2）。"""
    _require_group_chat(group_chat_id, authorization)
    return list_messages(group_chat_id)


@router.post(
    "/{group_chat_id}/task-clarifications",
    response_model=TaskClarificationResponse,
)
def create_task_clarification_route(
    group_chat_id: str,
    request: TaskClarificationRequest,
    authorization: str | None = Header(default=None),
) -> TaskClarificationResponse:
    """创建苏格拉底式任务澄清会话（design §5.3）。

    只创建 demo 澄清记录，不启动 run、不写正式 Memory。
    """
    _require_group_chat(group_chat_id, authorization, action="write")
    try:
        return create_task_clarification(group_chat_id, request)
    except (GroupChatMemberNotFoundError, GroupChatMissingPhDError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ClarificationRuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClarificationProtocolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/{group_chat_id}/task-clarifications",
    response_model=list[TaskClarificationResponse],
)
def list_task_clarifications_route(
    group_chat_id: str,
    authorization: str | None = Header(default=None),
) -> list[TaskClarificationResponse]:
    """Return server-persisted clarification sessions for a group chat."""
    _require_group_chat(group_chat_id, authorization)
    return list_clarifications(group_chat_id)


@router.post(
    "/{group_chat_id}/task-clarifications/{clarification_id}/answers",
    response_model=TaskClarificationResponse,
)
def answer_task_clarification_route(
    group_chat_id: str,
    clarification_id: str,
    request: TaskClarificationAnswerRequest,
    authorization: str | None = Header(default=None),
) -> TaskClarificationResponse:
    """提交一轮澄清回答并返回下一问题或完成状态。"""
    _require_group_chat(group_chat_id, authorization, action="write")
    try:
        return answer_task_clarification(group_chat_id, clarification_id, request)
    except ClarificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClarificationClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{group_chat_id}/task-clarifications/{clarification_id}/formal-task",
    response_model=FormalTaskContext,
)
def create_formal_task_route(
    group_chat_id: str,
    clarification_id: str,
    authorization: str | None = Header(default=None),
) -> FormalTaskContext:
    """Freeze a completed clarification into the formal task context."""
    _require_group_chat(group_chat_id, authorization, action="write")
    try:
        return create_formal_task(group_chat_id, clarification_id)
    except ClarificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClarificationClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
