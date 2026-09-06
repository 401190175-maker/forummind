"""真组会预演正式状态隔离测试（tasks.md Task 8）。"""

import pytest
from fastapi.testclient import TestClient

from app.api.runs import run_store
from app.group_chats.creation_service import reset_created_group_chats
from app.group_chats.messages import list_clarifications, list_messages, reset_messages
from app.main import app
from app.meeting_rehearsal.service import reset_rehearsals


@pytest.fixture(autouse=True)
def _reset_demo_stores():
    reset_rehearsals()
    reset_created_group_chats()
    reset_messages()
    run_store.reset()
    yield
    reset_rehearsals()
    reset_created_group_chats()
    reset_messages()
    run_store.reset()


def _create_group_chat(client: TestClient) -> str:
    response = client.post(
        "/group-chats",
        json={
            "topic_name": "预演状态隔离课题组",
            "topic_summary": "验证泥浆条件、气泡稳定与孔结构的关系",
            "data_space": "synthetic",
            "member_selection": {
                "postdoc": {"selection_mode": "generate", "count": 1},
                "phd_student": {"selection_mode": "generate", "count": 1},
                "master_student": {"selection_mode": "generate", "count": 3},
            },
        },
    )
    assert response.status_code == 200
    return response.json()["group_chat"]["id"]


def _formal_run_snapshot(snapshot: dict) -> dict:
    return {
        "status": snapshot["status"],
        "phase": snapshot["phase"],
        "cycle": snapshot["cycle"],
        "step_ids": [step["id"] for step in snapshot["steps"]],
        "memory_ids": [entry["id"] for entry in snapshot["memory"]],
    }


def test_rehearsal_does_not_change_formal_run_or_chat_records() -> None:
    client = TestClient(app)
    group_chat_id = _create_group_chat(client)
    run_response = client.post(
        f"/group-chats/{group_chat_id}/runs",
        json={"mode": "replay"},
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    before = client.get(f"/runs/{run_id}").json()
    before_messages = list_messages(group_chat_id)
    before_clarifications = list_clarifications(group_chat_id)

    rehearsal_response = client.post(
        f"/group-chats/{group_chat_id}/meeting-rehearsals",
        json={"run_id": run_id, "max_questions": 3},
    )
    assert rehearsal_response.status_code == 200
    session = rehearsal_response.json()

    for question in session["questions"]:
        answer_response = client.post(
            f"/meeting-rehearsals/{session['id']}/answers",
            json={
                "question_id": question["id"],
                "answer": f"围绕 {question['id']} 补充样品链、控制条件和判定顺序",
            },
        )
        assert answer_response.status_code == 200

    first_package = client.post(
        f"/meeting-rehearsals/{session['id']}/preparation-package"
    )
    second_package = client.post(
        f"/meeting-rehearsals/{session['id']}/preparation-package"
    )
    assert first_package.status_code == 200
    assert second_package.status_code == 200
    assert first_package.json() == second_package.json()

    after = client.get(f"/runs/{run_id}").json()
    assert _formal_run_snapshot(after) == _formal_run_snapshot(before)
    assert list_messages(group_chat_id) == before_messages
    assert list_clarifications(group_chat_id) == before_clarifications


def test_rehearsal_without_run_has_no_formal_state_to_mutate() -> None:
    client = TestClient(app)
    group_chat_id = _create_group_chat(client)

    response = client.post(
        f"/group-chats/{group_chat_id}/meeting-rehearsals",
        json={"max_questions": 3},
    )

    assert response.status_code == 200
    assert response.json()["run_id"] is None
    assert response.json()["record_scope"] == "rehearsal"
    assert response.json()["persistence"] == "not_persisted"
    assert list_messages(group_chat_id) == []
    assert list_clarifications(group_chat_id) == []
