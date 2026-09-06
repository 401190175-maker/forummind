"""HTTP contract for starting a task-scoped real Live Run from the workbench."""

from __future__ import annotations

import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import runs
from app.api.runs import router as runs_router
from app.domain.schemas import AgentProfile
from app.orchestration.run_store import RunStore
from app.storage.repositories import GroupChatRepository
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import ResearchTask


def test_live_workbench_request_binds_task_and_agent_without_replay(monkeypatch, tmp_path):
    store = SQLiteStore(tmp_path / "workbench-api.db")
    store.initialize()
    GroupChatRepository(store).save({
        "group_chat_id": "group-a",
        "data_space": "desensitized_real",
        "payload": {"group_chat": {"id": "group-a"}},
        "created_at": 1.0,
        "updated_at": 1.0,
    })
    task = ResearchTask(
        task_id="task-a", group_chat_id="group-a", title="Strength review",
        question="What trend does the source support?", document_ids=[],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    )
    ResearchTaskRepository(store).create(task)

    agent = AgentProfile(
        agent_id="agent-a", name="Evidence Analyst", role="master_student",
        primary_ability="evidence review", allowed_data_spaces=["desensitized_real"],
        allowed_tools=["knowledge.search"],
    )
    member = SimpleNamespace(
        role="master_student", selection_mode="existing", status="active",
        agent_profile_ref=SimpleNamespace(object_id="agent-a"),
    )
    monkeypatch.setattr(
        runs,
        "get_created_group_chat",
        lambda _group_id: SimpleNamespace(members=[member]),
    )
    monkeypatch.setattr(
        runs.agents_service,
        "get_agent_record",
        lambda _agent_id: {"enabled": True, "profile": agent.model_dump(mode="json")},
    )
    invoked = threading.Event()
    received: dict[str, object] = {}

    async def fake_run_live_task(task_value, agent_value, **kwargs):
        received["task_id"] = task_value.task_id
        received["agent_id"] = agent_value.agent_id
        received["mode"] = kwargs["state"].mode
        invoked.set()
        return kwargs["state"]

    monkeypatch.setattr(runs, "run_live_task", fake_run_live_task)
    previous_store = runs.run_store
    previous_configured_store = getattr(runs, "_store", None)
    runs.run_store = RunStore(store)
    runs.configure_persistence(store)
    app = FastAPI()
    app.include_router(runs_router)

    try:
        response = TestClient(app).post(
            "/group-chats/group-a/runs",
            json={"mode": "live", "task_id": "task-a", "agent_id": "agent-a"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert invoked.wait(2)
        assert received == {"task_id": "task-a", "agent_id": "agent-a", "mode": "live"}
    finally:
        runs.run_store = previous_store
        runs.configure_persistence(previous_configured_store)
        store.close()
