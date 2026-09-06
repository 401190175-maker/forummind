"""真组会预演 HTTP router 测试（tasks.md Task 6）。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import meeting_rehearsal as api
from app.meeting_rehearsal.schemas import (
    MeetingRehearsalSession,
    PreparationPackage,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def _session() -> MeetingRehearsalSession:
    return MeetingRehearsalSession(
        id="rehearsal-1",
        group_chat_id="gc-1",
        questions=[],
    )


def _package() -> PreparationPackage:
    return PreparationPackage(
        session_id="rehearsal-1",
        group_chat_id="gc-1",
        likely_questions=[],
        answer_summaries=[],
        weak_points=[],
        suggested_materials=[],
        action_items=[],
        source_refs=[],
        boundary_statement="模拟准备记录，不代表正式组会记录或 PI 决策",
    )


def test_create_rehearsal_route_returns_session(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(api, "create_rehearsal", lambda group_chat_id, request: _session())

    response = client.post(
        "/group-chats/gc-1/meeting-rehearsals",
        json={"max_questions": 3},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "rehearsal-1"
    assert response.json()["record_scope"] == "rehearsal"
    assert response.json()["persistence"] == "not_persisted"


def test_get_missing_rehearsal_returns_404(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(api, "get_rehearsal", lambda session_id: None)

    response = client.get("/meeting-rehearsals/missing")

    assert response.status_code == 404


def test_submit_answer_route_returns_updated_session(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(api, "submit_answer", lambda session_id, request: _session())

    response = client.post(
        "/meeting-rehearsals/rehearsal-1/answers",
        json={"question_id": "question-1", "answer": "补齐样品链"},
    )

    assert response.status_code == 200
    assert response.json()["record_scope"] == "rehearsal"


def test_submit_answer_rejects_blank_answer(client: TestClient) -> None:
    response = client.post(
        "/meeting-rehearsals/rehearsal-1/answers",
        json={"question_id": "question-1", "answer": "   "},
    )

    assert response.status_code == 422


def test_package_route_returns_preparation_package(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(api, "build_package", lambda session_id: _package())

    response = client.post(
        "/meeting-rehearsals/rehearsal-1/preparation-package"
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "rehearsal-1"
    assert response.json()["boundary_statement"]
