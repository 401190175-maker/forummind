"""Agent lifecycle and Pi test task behavior."""

import asyncio

import pytest

from app.agent_runtime.pi_client import (
    PiProtocolError,
    PiTimeoutError,
    PiUnavailableError,
)
from app.agent_runtime.pi_runtime import PiRuntime
from app.agents.service import (
    AgentDisabledError,
    AgentService,
    DuplicateAgentError,
)
from app.domain.schemas import AgentProfile, AgentRole
from app.storage.repositories import AgentRepository
from app.storage.sqlite_store import SQLiteStore


def profile(agent_id: str = "agent-custom") -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        name="自定义 Agent",
        role=AgentRole.MASTER_STUDENT,
    )


class FakePiClient:
    def __init__(self, response: object | BaseException) -> None:
        self.response = response
        self.requests: list[dict] = []

    async def invoke(self, request: dict) -> object:
        self.requests.append(request)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def test_create_update_enable_and_disable_agent(tmp_path):
    store = SQLiteStore(tmp_path / "agents.db")
    store.initialize()
    service = AgentService(store=store)

    assert service.create_agent(profile()).agent_id == "agent-custom"
    with pytest.raises(DuplicateAgentError):
        service.create_agent(profile())

    updated = service.update_agent(
        "agent-custom", {"name": "更新后的 Agent", "enabled": False}
    )
    assert updated.name == "更新后的 Agent"
    assert service.get_agent_record("agent-custom")["enabled"] is False
    with pytest.raises(AgentDisabledError):
        asyncio.run(service.test_agent("agent-custom", "测试"))

    service.set_agent_enabled("agent-custom", True)
    assert service.get_agent_record("agent-custom")["enabled"] is True
    store.close()


def test_test_agent_sends_minimal_profile_and_persists_ready_result(tmp_path):
    store = SQLiteStore(tmp_path / "agents.db")
    store.initialize()
    client = FakePiClient(
        {"agent_id": "agent-custom", "content": "可执行的候选回答"}
    )
    service = AgentService(store=store, runtime=PiRuntime(client))
    service.create_agent(profile())

    result = asyncio.run(service.test_agent("agent-custom", "请说明你的分析边界"))

    assert result.status == "ready"
    assert result.agent_id == "agent-custom"
    assert result.runtime == "pi"
    assert result.result == "可执行的候选回答"
    assert result.duration_ms >= 0
    request = client.requests[0]
    assert request["agent_id"] == "agent-custom"
    assert request["task"] == "请说明你的分析边界"
    assert request["data_space"] == "synthetic"
    assert request["allowed_tools"] == []
    assert request["context"]["agent_profile"]["name"] == "自定义 Agent"
    assert request["agent_instruction"]["agent_id"] == "agent-custom"
    assert "自定义 Agent" in request["agent_instruction"]["identity"]
    assert "PI_API_KEY" not in repr(request)
    test_id = result.test_id
    store.close()

    reopened = SQLiteStore(tmp_path / "agents.db")
    reopened.initialize()
    recovered = AgentService(store=reopened).get_test_result(test_id)
    assert recovered is not None
    assert recovered.status == "ready"
    assert recovered.result == "可执行的候选回答"
    reopened.close()


def test_get_latest_test_result_uses_created_at_then_test_id_ordering(tmp_path):
    store = SQLiteStore(tmp_path / "agents.db")
    store.initialize()
    repository = AgentRepository(store)
    repository.save_test_result(
        {
            "test_id": "agent-test-999",
            "agent_id": "agent-custom",
            "status": "failed",
            "runtime": "pi",
            "result": "",
            "error": "earlier",
            "duration_ms": 4,
            "created_at": 100.0,
        }
    )
    repository.save_test_result(
        {
            "test_id": "agent-test-001",
            "agent_id": "agent-custom",
            "status": "ready",
            "runtime": "pi",
            "result": "latest",
            "error": "",
            "duration_ms": 3,
            "created_at": 200.0,
        }
    )
    repository.save_test_result(
        {
            "test_id": "agent-test-002",
            "agent_id": "agent-custom",
            "status": "ready",
            "runtime": "pi",
            "result": "latest-tie-breaker",
            "error": "",
            "duration_ms": 2,
            "created_at": 200.0,
        }
    )

    latest = AgentService(store=store).get_latest_test_result("agent-custom")

    assert latest is not None
    assert latest.test_id == "agent-test-002"
    assert latest.status == "ready"
    assert latest.result == "latest-tie-breaker"
    assert AgentService(store=store).get_latest_test_result("missing") is None
    store.close()


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (PiUnavailableError("sidecar unavailable"), "unavailable"),
        (PiTimeoutError("Pi request timeout"), "unavailable"),
        (PiProtocolError("invalid Pi envelope"), "failed"),
    ],
)
def test_test_agent_persists_explainable_pi_failure(
    tmp_path, failure, expected_status
):
    store = SQLiteStore(tmp_path / "agents.db")
    store.initialize()
    service = AgentService(
        store=store,
        runtime=PiRuntime(FakePiClient(failure)),
    )
    service.create_agent(profile())

    result = asyncio.run(service.test_agent("agent-custom", "测试 Pi"))

    assert result.status == expected_status
    assert result.runtime == "pi"
    assert result.result == ""
    assert result.error
    assert service.get_test_result(result.test_id).status == expected_status
    store.close()
