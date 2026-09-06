"""课题组删除与生成成员确认的生命周期测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import service as agents_service
from app.api import runs as runs_api
from app.api.group_chats import router as group_chats_router
from app.demo_data.loader import load_demo_package
from app.demo_data.object_factory import build_agent_profiles
from app.domain.schemas import DataSpace
from app.group_chats import creation_service
from app.storage.repositories import ArtifactRepository, MeetingRepository, MessageRepository
from app.storage.sqlite_store import SQLiteStore


_PAYLOAD = {
    "topic_name": "生命周期测试课题组",
    "topic_summary": "验证课题组删除和生成成员确认",
    "member_selection": {
        "postdoc": {"selection_mode": "existing", "agent_ids": ["agent-postdoc-1"]},
        "phd_student": {"selection_mode": "existing", "agent_ids": ["agent-phd-1"]},
        "master_student": {"selection_mode": "generate", "count": 3},
    },
}


def _test_app() -> FastAPI:
    application = FastAPI()
    application.include_router(group_chats_router)
    application.include_router(runs_api.router)
    return application


def test_delete_group_chat_removes_detail_messages_runs_events_and_artifacts(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    previous_group_store = creation_service._persistence_store
    previous_agent_service = agents_service._default_service
    previous_run_store = runs_api.run_store._persistence_store
    previous_meeting_store = (
        runs_api._meeting_repository.store if runs_api._meeting_repository else None
    )
    creation_service.configure_persistence(store)
    agents_service.configure_persistence(
        store,
        seed_profiles=build_agent_profiles(load_demo_package("foam_concrete_case")),
    )
    runs_api.run_store.configure_persistence(store)
    runs_api.configure_persistence(store)
    client = TestClient(_test_app())
    try:
        created = client.post("/group-chats", json=_PAYLOAD)
        assert created.status_code == 200
        group_chat_id = created.json()["group_chat"]["id"]
        client.post(
            f"/group-chats/{group_chat_id}/messages",
            json={"content": "待清理消息"},
        )
        run = runs_api.run_store.create(group_chat_id, "replay")
        MeetingRepository(store).append_event(
            {
                "event_id": "meeting:delete-test",
                "run_id": run.run_id,
                "actor_id": "PI",
                "actor_role": "pi",
                "kind": "message",
                "content": "待清理会议事件",
                "timestamp": 1.0,
                "source": "pi",
                "source_refs": ["pi:meeting:delete-test"],
            }
        )
        ArtifactRepository(store).save(
            {
                "artifact_id": "artifact:delete-test",
                "run_id": run.run_id,
                "group_chat_id": group_chat_id,
                "agent_id": "agent-ms-1",
                "artifact_type": "master_research_markdown",
                "filename": "delete-test.md",
                "content": "# 待清理",
                "data_space": "synthetic",
                "created_at": 1.0,
                "updated_at": 1.0,
            }
        )

        response = client.delete(f"/group-chats/{group_chat_id}")

        assert response.status_code == 200
        assert response.json() == {"deleted": True, "group_chat_id": group_chat_id}
        assert client.get(f"/group-chats/{group_chat_id}").status_code == 404
        assert client.get(f"/group-chats/{group_chat_id}/messages").status_code == 404
        assert runs_api.run_store.get(run.run_id) is None
        assert MessageRepository(store).list(group_chat_id) == []
        assert MeetingRepository(store).list_events(run.run_id) == []
        assert ArtifactRepository(store).list_for_run(run.run_id) == []
    finally:
        creation_service._created_group_chats.clear()
        creation_service._persistence_store = previous_group_store
        creation_service._group_chat_repository = (
            None
            if previous_group_store is None
            else creation_service.GroupChatRepository(previous_group_store)
        )
        agents_service._default_service = previous_agent_service
        runs_api.run_store.reset()
        runs_api.run_store.configure_persistence(previous_run_store)
        runs_api.configure_persistence(previous_meeting_store)
        store.close()


def test_confirm_generated_member_creates_persistent_agent_and_is_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "forummind.db")
    store.initialize()
    previous_group_store = creation_service._persistence_store
    previous_agent_service = agents_service._default_service
    creation_service.configure_persistence(store)
    agents_service.configure_persistence(
        store,
        seed_profiles=build_agent_profiles(load_demo_package("foam_concrete_case")),
    )
    client = TestClient(_test_app())
    try:
        created = client.post("/group-chats", json=_PAYLOAD)
        assert created.status_code == 200
        group_chat_id = created.json()["group_chat"]["id"]
        member_id = next(
            member["id"]
            for member in created.json()["members"]
            if member["role"] == "master_student"
        )
        payload = {
            "display_name": "证据 Agent",
            "primary_ability": "证据核查",
            "description": "核查证据边界",
            "secondary_abilities": ["样品对应关系分析"],
            "general_research_abilities": ["实验设计"],
            "allowed_tools": [
                "knowledge.search",
                "experiment.analyze",
                "literature.search",
            ],
            "specialty_domain": "泡沫混凝土孔结构",
            "knowledge_base_coverage": "已核验的合成案例资料",
            "forbidden_actions": "不得把相关性写成因果结论",
        }

        first = client.patch(
            f"/group-chats/{group_chat_id}/members/{member_id}/configuration",
            json=payload,
        )
        second = client.patch(
            f"/group-chats/{group_chat_id}/members/{member_id}/configuration",
            json=payload,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        first_member = next(item for item in first.json()["members"] if item["id"] == member_id)
        second_member = next(item for item in second.json()["members"] if item["id"] == member_id)
        assert first_member["status"] == "active"
        assert second_member["status"] == "active"
        assert second_member["agent_profile_ref"] == first_member["agent_profile_ref"]
        agent_id = second_member["agent_profile_ref"]["object_id"].rsplit(":", 1)[-1]
        profile = agents_service.get_agent(agent_id)
        assert profile.name == "证据 Agent"
        assert profile.secondary_abilities == ["样品对应关系分析"]
        assert profile.general_research_abilities == ["实验设计"]
        assert profile.allowed_data_spaces == [DataSpace.DESENSITIZED_REAL]
        assert profile.allowed_tools == [
            "knowledge.search",
            "experiment.analyze",
            "literature.search",
        ]
        assert profile.specialty_domain == "泡沫混凝土孔结构"
        assert profile.knowledge_base_coverage == "已核验的合成案例资料"
        assert profile.forbidden_actions == "不得把相关性写成因果结论"
    finally:
        creation_service._created_group_chats.clear()
        creation_service._persistence_store = previous_group_store
        creation_service._group_chat_repository = (
            None
            if previous_group_store is None
            else creation_service.GroupChatRepository(previous_group_store)
        )
        agents_service._default_service = previous_agent_service
        store.close()
