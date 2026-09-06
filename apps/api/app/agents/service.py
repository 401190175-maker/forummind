"""Persistent Agent lifecycle and one-shot Pi test services."""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from app.agent_runtime.base import AgentRuntime
from app.agent_runtime.factory import create_runtime
from app.agent_runtime.pi_client import (
    PiAuthError,
    PiClientError,
    PiProtocolError,
    PiTimeoutError,
    PiUnavailableError,
)
from app.agent_runtime.runtime_policy import resolve_runtime_policy
from app.agent_runtime.schemas import AgentInvocation, AgentResult, RuntimeSelection
from app.agent_runtime.instruction_builder import build_agent_instruction
from app.domain.schemas import AgentProfile
from app.storage.repositories import AgentRepository
from app.storage.sqlite_store import SQLiteStore


class AgentServiceError(Exception):
    """Base class for Agent lifecycle service errors."""


class AgentNotFoundError(AgentServiceError):
    """The requested Agent does not exist."""


class DuplicateAgentError(AgentServiceError):
    """An Agent with the requested stable ID already exists."""


class AgentDisabledError(AgentServiceError):
    """A disabled Agent cannot execute a test task."""


class AgentPatchError(AgentServiceError):
    """The lifecycle patch is not valid for an AgentProfile."""


class AgentTaskError(AgentServiceError):
    """The test task is blank or otherwise invalid."""


class AgentTestResult(BaseModel):
    """Persisted outcome of one controlled Agent test invocation."""

    test_id: str
    agent_id: str
    status: Literal["ready", "unavailable", "failed"]
    runtime: str
    result: str = ""
    error: str = ""
    duration_ms: int = Field(ge=0)
    created_at: float


class AgentService:
    """Manage Agent profiles and execute isolated Pi test tasks."""

    def __init__(
        self,
        store: SQLiteStore | None = None,
        *,
        repository: AgentRepository | None = None,
        runtime: AgentRuntime | None = None,
        runtime_factory: Callable[[RuntimeSelection], AgentRuntime | None] = create_runtime,
        policy_resolver: Callable[..., RuntimeSelection] = resolve_runtime_policy,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._repository = repository or (AgentRepository(store) if store is not None else None)
        self._runtime = runtime
        self._runtime_factory = runtime_factory
        self._policy_resolver = policy_resolver
        self._clock = clock
        self._agents: dict[str, dict] = {}
        self._test_results: dict[str, AgentTestResult] = {}

    def create_agent(self, profile: AgentProfile) -> AgentProfile:
        profile = AgentProfile.model_validate(profile)
        if not profile.agent_id.strip():
            raise AgentPatchError("agent_id must be a non-empty stable identifier")
        now = self._clock()
        profile_data = profile.model_dump(mode="json")
        try:
            if self._repository is not None:
                self._repository.create(
                    profile_data,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            elif profile.agent_id in self._agents:
                raise DuplicateAgentError(profile.agent_id)
            else:
                self._agents[profile.agent_id] = {
                    "agent_id": profile.agent_id,
                    "profile": profile_data,
                    "enabled": True,
                    "created_at": now,
                    "updated_at": now,
                }
        except sqlite3.IntegrityError as exc:
            raise DuplicateAgentError(profile.agent_id) from exc
        return profile

    def get_agent_record(self, agent_id: str) -> dict | None:
        if self._repository is not None:
            return self._repository.get(agent_id)
        record = self._agents.get(agent_id)
        return None if record is None else dict(record)

    def get_agent(self, agent_id: str) -> AgentProfile | None:
        record = self.get_agent_record(agent_id)
        if record is None:
            return None
        return AgentProfile.model_validate(record["profile"])

    def list_agent_records(self) -> list[dict]:
        if self._repository is not None:
            return self._repository.list()
        return [dict(record) for record in self._agents.values()]

    def list_agents(self) -> list[AgentProfile]:
        return [
            AgentProfile.model_validate(record["profile"])
            for record in self.list_agent_records()
        ]

    def update_agent(self, agent_id: str, patch: dict) -> AgentProfile:
        record = self._require_record(agent_id)
        if not isinstance(patch, Mapping):
            raise AgentPatchError("agent patch must be a JSON object")
        patch = dict(patch)
        if "agent_id" in patch and patch["agent_id"] != agent_id:
            raise AgentPatchError("agent_id is immutable")
        allowed_profile_fields = set(AgentProfile.model_fields)
        unknown_fields = set(patch) - allowed_profile_fields - {"enabled"}
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise AgentPatchError(f"unknown Agent fields: {names}")
        if "enabled" in patch and type(patch["enabled"]) is not bool:
            raise AgentPatchError("enabled must be a boolean")

        profile_data = dict(record["profile"])
        profile_data.update(
            {key: value for key, value in patch.items() if key != "enabled"}
        )
        try:
            profile = AgentProfile.model_validate(profile_data)
        except Exception as exc:
            raise AgentPatchError(str(exc)) from exc
        enabled = patch.get("enabled", record["enabled"])
        self._save_agent(agent_id, profile, enabled=enabled)
        return profile

    def set_agent_enabled(self, agent_id: str, enabled: bool) -> AgentProfile:
        if type(enabled) is not bool:
            raise AgentPatchError("enabled must be a boolean")
        record = self._require_record(agent_id)
        profile = AgentProfile.model_validate(record["profile"])
        self._save_agent(agent_id, profile, enabled=enabled)
        return profile

    async def test_agent(self, agent_id: str, task: str) -> AgentTestResult:
        record = self._require_record(agent_id)
        if not record["enabled"]:
            raise AgentDisabledError(agent_id)
        if not isinstance(task, str) or not task.strip():
            raise AgentTaskError("task must be non-empty text")

        profile = AgentProfile.model_validate(record["profile"])
        profile_version = str(record.get("updated_at", "current"))
        instruction = build_agent_instruction(
            profile,
            profile_version=profile_version,
            topic_context={},
            task_context={"agent_profile": profile.model_dump(mode="json")},
            phase="agent_test",
            output_contract="free_text",
        )
        test_id = f"agent-test-{uuid.uuid4().hex[:12]}"
        started = time.perf_counter()
        runtime_name = "pi"
        invocation = AgentInvocation(
            run_id=test_id,
            group_chat_id="",
            cycle=None,
            phase="agent_test",
            agent_id=profile.agent_id,
            role=profile.role.value,
            profile_version=profile_version,
            agent_instruction=instruction,
            task=task.strip(),
            context={"agent_profile": profile.model_dump(mode="json")},
            allowed_tools=[],
            output_contract="free_text",
            data_space="synthetic",
            safety_rules=[
                "no_formal_memory_write",
                "no_stage_transition",
                "no_external_data_access",
            ],
        )

        if self._runtime is None:
            selection = self._policy_resolver("live", require_pi=True)
            runtime_name = selection.runtime_name
            if runtime_name == "unavailable":
                return self._persist_result(
                    test_id=test_id,
                    agent_id=agent_id,
                    status="unavailable",
                    runtime=runtime_name,
                    error=selection.fallback_reason or "Pi runtime is unavailable",
                    duration_ms=self._duration_ms(started),
                )
            runtime = self._runtime_factory(selection)
            if runtime is None:
                return self._persist_result(
                    test_id=test_id,
                    agent_id=agent_id,
                    status="unavailable",
                    runtime="unavailable",
                    error="Pi runtime factory returned no runtime",
                    duration_ms=self._duration_ms(started),
                )
        else:
            runtime = self._runtime

        try:
            result = await runtime.invoke(invocation)
        except PiUnavailableError as exc:
            return self._persist_result(
                test_id=test_id,
                agent_id=agent_id,
                status="unavailable",
                runtime=runtime_name,
                error=str(exc),
                duration_ms=self._duration_ms(started),
            )
        except (PiTimeoutError, PiProtocolError, PiAuthError, PiClientError) as exc:
            return self._persist_result(
                test_id=test_id,
                agent_id=agent_id,
                status="unavailable" if isinstance(exc, PiTimeoutError) else "failed",
                runtime=runtime_name,
                error=str(exc),
                duration_ms=self._duration_ms(started),
            )
        except Exception as exc:
            return self._persist_result(
                test_id=test_id,
                agent_id=agent_id,
                status="failed",
                runtime=runtime_name,
                error=f"Agent runtime error: {exc}",
                duration_ms=self._duration_ms(started),
            )

        status, error, content = self._map_agent_result(invocation, result)
        return self._persist_result(
            test_id=test_id,
            agent_id=agent_id,
            status=status,
            runtime=runtime_name,
            result=content,
            error=error,
            duration_ms=self._duration_ms(started),
        )

    def get_test_result(self, test_id: str) -> AgentTestResult | None:
        if self._repository is not None:
            record = self._repository.get_test_result(test_id)
            return None if record is None else AgentTestResult.model_validate(record)
        return self._test_results.get(test_id)

    def get_latest_test_result(self, agent_id: str) -> AgentTestResult | None:
        if self._repository is not None:
            record = self._repository.get_latest_test_result(agent_id)
            return None if record is None else AgentTestResult.model_validate(record)
        return max(
            (
                result
                for result in self._test_results.values()
                if result.agent_id == agent_id
            ),
            key=lambda result: (result.created_at, result.test_id),
            default=None,
        )

    def seed_profiles(self, profiles: Sequence[AgentProfile]) -> None:
        """Add initial profiles without overwriting user-managed records."""
        for profile in profiles:
            if not profile.agent_id.strip() or self.get_agent_record(profile.agent_id):
                continue
            try:
                self.create_agent(profile)
            except DuplicateAgentError:
                continue

    def _require_record(self, agent_id: str) -> dict:
        record = self.get_agent_record(agent_id)
        if record is None:
            raise AgentNotFoundError(agent_id)
        return record

    def _save_agent(self, agent_id: str, profile: AgentProfile, *, enabled: bool) -> None:
        now = self._clock()
        profile_data = profile.model_dump(mode="json")
        if self._repository is not None:
            self._repository.update(
                agent_id,
                profile_data,
                enabled=enabled,
                updated_at=now,
            )
            return
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        record = self._agents[agent_id]
        record.update(profile=profile_data, enabled=enabled, updated_at=now)

    def _persist_result(
        self,
        *,
        test_id: str,
        agent_id: str,
        status: Literal["ready", "unavailable", "failed"],
        runtime: str,
        result: str = "",
        error: str = "",
        duration_ms: int,
    ) -> AgentTestResult:
        record = AgentTestResult(
            test_id=test_id,
            agent_id=agent_id,
            status=status,
            runtime=runtime,
            result=result,
            error=error,
            duration_ms=duration_ms,
            created_at=self._clock(),
        )
        if self._repository is not None:
            self._repository.save_test_result(record.model_dump(mode="json"))
        else:
            self._test_results[test_id] = record
        return record

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(int((time.perf_counter() - started) * 1000), 0)

    @staticmethod
    def _map_agent_result(
        invocation: AgentInvocation, result: AgentResult
    ) -> tuple[Literal["ready", "unavailable", "failed"], str, str]:
        if not isinstance(result, AgentResult):
            return "failed", "Pi runtime returned an invalid AgentResult", ""
        error_code = getattr(result, "error_code", "")
        if error_code in {"pi_unavailable", "pi_timeout"}:
            return (
                "unavailable",
                result.error or (result.warnings[0] if result.warnings else "Pi is unavailable"),
                "",
            )
        if result.status != "ok":
            message = result.error or (result.warnings[0] if result.warnings else "Pi returned an error")
            lowered = message.lower()
            if "timeout" in lowered or "unavailable" in lowered:
                return "unavailable", message, ""
            return "failed", message, ""
        if result.agent_id != invocation.agent_id:
            return "failed", "Agent ID mismatch in Pi result", ""
        if result.data_space != invocation.data_space:
            return "failed", "data_space mismatch in Pi result", ""
        if not result.content.strip():
            return "failed", "Pi result content must not be empty", ""
        return "ready", "", result.content


_default_service = AgentService()


def configure_persistence(
    store: SQLiteStore | None,
    *,
    seed_profiles: Sequence[AgentProfile] | None = None,
) -> None:
    """Attach the application SQLite store and seed missing demo profiles."""
    global _default_service
    _default_service = AgentService(store=store)
    if seed_profiles is None:
        from app.demo_data.loader import load_demo_package
        from app.demo_data.object_factory import build_agent_profiles

        seed_profiles = build_agent_profiles(
            load_demo_package("foam_concrete_case")
        )
    _default_service.seed_profiles(seed_profiles)


def create_agent(profile: AgentProfile) -> AgentProfile:
    return _default_service.create_agent(profile)


def get_agent(agent_id: str) -> AgentProfile | None:
    return _default_service.get_agent(agent_id)


def get_agent_record(agent_id: str) -> dict | None:
    return _default_service.get_agent_record(agent_id)


def list_agents() -> list[AgentProfile]:
    return _default_service.list_agents()


def list_agent_records() -> list[dict]:
    return _default_service.list_agent_records()


def update_agent(agent_id: str, patch: dict) -> AgentProfile:
    return _default_service.update_agent(agent_id, patch)


def set_agent_enabled(agent_id: str, enabled: bool) -> AgentProfile:
    return _default_service.set_agent_enabled(agent_id, enabled)


async def test_agent(agent_id: str, task: str) -> AgentTestResult:
    return await _default_service.test_agent(agent_id, task)


def get_test_result(test_id: str) -> AgentTestResult | None:
    return _default_service.get_test_result(test_id)


def get_latest_test_result(agent_id: str) -> AgentTestResult | None:
    return _default_service.get_latest_test_result(agent_id)
