"""Runtime factory tests (Task 6)."""

import pytest

from app.agent_runtime.factory import create_runtime
from app.agent_runtime.legacy_llm_runtime import LegacyLLMRuntime
from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.native_pi_client import NativePiClient
from app.agent_runtime.pi_runtime import PiRuntime
from app.agent_runtime.schemas import RuntimeSelection
from app.tools import build_synthetic_registry


def test_create_runtime_defaults_to_legacy_llm() -> None:
    assert isinstance(create_runtime(), LegacyLLMRuntime)


def test_create_runtime_treats_empty_env_as_default(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME", "")
    assert isinstance(create_runtime(), LegacyLLMRuntime)


def test_create_runtime_legacy_llm_by_name() -> None:
    assert isinstance(create_runtime("legacy_llm"), LegacyLLMRuntime)


def test_create_runtime_mock_by_name() -> None:
    assert isinstance(create_runtime("mock"), MockRuntime)


def test_create_runtime_accepts_runtime_selection() -> None:
    selection = RuntimeSelection(
        api_mode="auto",
        resolved_mode="live",
        runtime_name="legacy_llm",
    )
    assert isinstance(create_runtime(selection), LegacyLLMRuntime)


def test_create_runtime_returns_none_for_replay_selection() -> None:
    selection = RuntimeSelection(api_mode="replay", resolved_mode="replay")
    assert create_runtime(selection) is None


def test_create_runtime_preserves_injected_runtime_instance() -> None:
    runtime = MockRuntime()
    assert create_runtime(runtime) is runtime


def test_create_runtime_rejects_unknown_runtime_name() -> None:
    with pytest.raises(ValueError):
        create_runtime("surprise")


def test_create_runtime_pi_with_complete_configuration(monkeypatch) -> None:
    monkeypatch.setenv("PI_ENABLED", "true")
    monkeypatch.setenv("PI_MODEL", "pi-model")
    monkeypatch.setenv("PI_BASE_URL", "http://127.0.0.1:8787/invoke")
    monkeypatch.setenv("PI_API_KEY", "pi-key")

    runtime = create_runtime("pi")

    assert isinstance(runtime, PiRuntime)


def test_create_runtime_injects_p2_tools_into_pi(monkeypatch) -> None:
    monkeypatch.setenv("PI_ENABLED", "true")
    monkeypatch.setenv("PI_MODEL", "pi-model")
    monkeypatch.setenv("PI_BASE_URL", "http://127.0.0.1:8787/invoke")
    registry = build_synthetic_registry()
    context_factory = lambda invocation: None
    runtime = create_runtime("pi", tool_registry=registry, context_factory=context_factory)
    assert isinstance(runtime, PiRuntime)
    assert runtime._tool_registry is registry
    assert runtime._context_factory is context_factory


def test_create_runtime_gives_native_prompts_the_sidecar_timeout_budget(monkeypatch) -> None:
    monkeypatch.setenv("PI_ENABLED", "true")
    monkeypatch.setenv("PI_MODEL", "pi-model")
    monkeypatch.setenv("PI_RUNTIME_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("PI_RUNTIME_TOKEN", "runtime-token")
    monkeypatch.setenv("PI_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("PI_PROMPT_TIMEOUT_MS", "10000")

    runtime = create_runtime("pi")

    assert isinstance(runtime, PiRuntime)
    assert isinstance(runtime._client, NativePiClient)
    assert runtime._client.timeout == 5
    assert runtime._client.prompt_timeout == 15


def test_create_runtime_default_native_prompt_budget_allows_long_provider_runs(monkeypatch) -> None:
    monkeypatch.setenv("PI_ENABLED", "true")
    monkeypatch.setenv("PI_MODEL", "pi-model")
    monkeypatch.setenv("PI_RUNTIME_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("PI_RUNTIME_TOKEN", "runtime-token")
    monkeypatch.setenv("PI_TIMEOUT_SECONDS", "60")
    monkeypatch.delenv("PI_PROMPT_TIMEOUT_MS", raising=False)

    runtime = create_runtime("pi")

    assert isinstance(runtime, PiRuntime)
    assert isinstance(runtime._client, NativePiClient)
    assert runtime._client.prompt_timeout > 150


def test_create_runtime_selection_pi_with_complete_configuration(monkeypatch) -> None:
    monkeypatch.setenv("PI_ENABLED", "true")
    monkeypatch.setenv("PI_MODEL", "pi-model")
    monkeypatch.setenv("PI_BASE_URL", "http://127.0.0.1:8787/invoke")
    monkeypatch.setenv("PI_API_KEY", "pi-key")
    selection = RuntimeSelection(
        api_mode="auto",
        resolved_mode="live",
        runtime_name="pi",
    )

    assert isinstance(create_runtime(selection), PiRuntime)


def test_create_runtime_pi_incomplete_configuration_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PI_ENABLED", "true")
    monkeypatch.delenv("PI_MODEL", raising=False)
    monkeypatch.delenv("PI_BASE_URL", raising=False)
    monkeypatch.delenv("PI_API_KEY", raising=False)

    runtime = create_runtime("pi")

    assert runtime is None


def test_create_runtime_unknown_environment_falls_back_to_legacy(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME", "surprise")

    runtime = create_runtime()

    assert isinstance(runtime, LegacyLLMRuntime)
