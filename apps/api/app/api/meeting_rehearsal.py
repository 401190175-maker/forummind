"""真组会预演 HTTP router。"""

from fastapi import APIRouter, HTTPException

from app.meeting_rehearsal.schemas import (
    CreateMeetingRehearsalRequest,
    MeetingRehearsalSession,
    PreparationPackage,
    SubmitRehearsalAnswerRequest,
)
from app.meeting_rehearsal.service import (
    RehearsalClosedError,
    RehearsalGroupChatNotFoundError,
    RehearsalNotFoundError,
    RehearsalQuestionNotFoundError,
    RehearsalRunMismatchError,
    RehearsalRunNotFoundError,
    build_package,
    create_rehearsal,
    get_rehearsal,
    submit_answer,
)
from app.scenario.loader import ScenarioNotFound

router = APIRouter(tags=["meeting-rehearsal"])


@router.post(
    "/group-chats/{group_chat_id}/meeting-rehearsals",
    response_model=MeetingRehearsalSession,
)
def create_rehearsal_route(
    group_chat_id: str,
    request: CreateMeetingRehearsalRequest,
) -> MeetingRehearsalSession:
    try:
        return create_rehearsal(group_chat_id, request)
    except (RehearsalGroupChatNotFoundError, RehearsalRunNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RehearsalRunMismatchError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=500, detail="demo 剧本配置错误") from exc


@router.get(
    "/meeting-rehearsals/{session_id}",
    response_model=MeetingRehearsalSession,
)
def get_rehearsal_route(session_id: str) -> MeetingRehearsalSession:
    session = get_rehearsal(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="预演会话不存在")
    return session


@router.post(
    "/meeting-rehearsals/{session_id}/answers",
    response_model=MeetingRehearsalSession,
)
def submit_answer_route(
    session_id: str,
    request: SubmitRehearsalAnswerRequest,
) -> MeetingRehearsalSession:
    try:
        return submit_answer(session_id, request)
    except RehearsalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RehearsalQuestionNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RehearsalClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/meeting-rehearsals/{session_id}/preparation-package",
    response_model=PreparationPackage,
)
def build_package_route(session_id: str) -> PreparationPackage:
    try:
        return build_package(session_id)
    except RehearsalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
