"""真组会预演会话服务测试（tasks.md Task 5）。"""

from types import SimpleNamespace

import pytest

from app.domain.schemas import DataSpace
from app.meeting_rehearsal import service
from app.meeting_rehearsal.schemas import (
    CreateMeetingRehearsalRequest,
    RehearsalIntensity,
    SubmitRehearsalAnswerRequest,
)
from app.orchestration.run_store import RunState
from app.scenario.loader import load_scenario


def _group_chat(group_chat_id: str = "gc-1") -> SimpleNamespace:
    return SimpleNamespace(
        group_chat=SimpleNamespace(
            id=group_chat_id,
            data_space=DataSpace.SYNTHETIC,
        ),
        topic=SimpleNamespace(
            topic_name="废弃泥浆基泡沫混凝土",
            topic_summary="验证泥浆条件、气泡稳定与孔结构的关系",
        ),
    )


@pytest.fixture(autouse=True)
def _reset_rehearsals(monkeypatch: pytest.MonkeyPatch):
    original_run_store = service.run_store
    service.reset_rehearsals()
    monkeypatch.setattr(
        service,
        "get_created_group_chat",
        lambda group_chat_id: _group_chat(group_chat_id)
        if group_chat_id in {"gc-1", "gc-2"}
        else None,
    )
    monkeypatch.setattr(
        service,
        "load_scenario",
        lambda package_id: load_scenario(package_id),
    )
    yield
    service.run_store = original_run_store
    service.reset_rehearsals()


def _run(run_id: str = "run-1", group_chat_id: str = "gc-1") -> RunState:
    return RunState(
        run_id=run_id,
        group_chat_id=group_chat_id,
        mode="replay",
        status="awaiting_decision",
        phase="meeting",
        cycle=1,
    )


def test_create_rehearsal_without_run_returns_active_questions() -> None:
    session = service.create_rehearsal(
        "gc-1",
        CreateMeetingRehearsalRequest(
            intensity=RehearsalIntensity.GENTLE,
            max_questions=3,
        ),
    )

    assert session.group_chat_id == "gc-1"
    assert session.run_id is None
    assert session.status.value == "active"
    assert len(session.questions) == 3
    assert session.persistence == "not_persisted"


def test_submit_answer_appends_and_completes_session() -> None:
    service.run_store = SimpleNamespace(
        get=lambda run_id: _run(run_id) if run_id == "run-1" else None
    )
    session = service.create_rehearsal(
        "gc-1",
        CreateMeetingRehearsalRequest(run_id="run-1", max_questions=3),
    )

    for question in session.questions:
        service.submit_answer(
            session.id,
            SubmitRehearsalAnswerRequest(
                question_id=question.id,
                answer=f"针对 {question.id} 的样品链和控制条件回答",
            ),
        )

    completed = service.get_rehearsal(session.id)
    assert completed is not None
    assert completed.status.value == "completed"
    assert len(completed.answers) == 3
    assert len(completed.critiques) == 3
    assert all(question.status.value == "answered" for question in completed.questions)


def test_repeated_answer_is_appended_without_overwriting_history() -> None:
    session = service.create_rehearsal(
        "gc-1",
        CreateMeetingRehearsalRequest(max_questions=3),
    )
    request = SubmitRehearsalAnswerRequest(
        question_id=session.questions[0].id,
        answer="第一版回答",
    )
    service.submit_answer(session.id, request)
    service.submit_answer(
        session.id,
        SubmitRehearsalAnswerRequest(
            question_id=session.questions[0].id,
            answer="第二版回答",
        ),
    )

    current = service.get_rehearsal(session.id)
    assert current is not None
    assert [answer.content for answer in current.answers] == [
        "第一版回答",
        "第二版回答",
    ]


def test_build_package_is_repeatable_and_cached_on_session() -> None:
    session = service.create_rehearsal(
        "gc-1",
        CreateMeetingRehearsalRequest(max_questions=3),
    )

    first = service.build_package(session.id)
    second = service.build_package(session.id)
    current = service.get_rehearsal(session.id)

    assert first == second
    assert current is not None
    assert current.preparation_package == second


def test_create_rehearsal_rejects_run_from_another_group_chat() -> None:
    service.run_store = SimpleNamespace(get=lambda run_id: _run("run-2", "gc-2"))

    with pytest.raises(service.RehearsalRunMismatchError):
        service.create_rehearsal(
            "gc-1",
            CreateMeetingRehearsalRequest(run_id="run-2"),
        )
