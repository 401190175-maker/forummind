"""Runtime policy 测试（Agent Runtime Adapter 前置 Task 4）。"""

import inspect

import pytest

from app.agent_runtime.runtime_policy import resolve_runtime_policy


def test_replay_mode_does_not_require_runtime() -> None:
    selection = resolve_runtime_policy("replay", env={})
    assert selection.api_mode == "replay"
    assert selection.resolved_mode == "replay"
    assert selection.runtime_name == ""
    assert selection.fallback_reason == ""
    assert selection.warnings == []


def test_auto_without_pi_is_live_but_unavailable() -> None:
    selection = resolve_runtime_policy("auto", env={})
    assert selection.api_mode == "auto"
    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "AGENT_RUNTIME" in selection.fallback_reason


def test_auto_with_llm_key_does_not_select_legacy_live() -> None:
    selection = resolve_runtime_policy("auto", env={"LLM_API_KEY": "test-key"})
    assert selection.api_mode == "auto"
    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "AGENT_RUNTIME" in selection.fallback_reason


def test_auto_with_complete_enabled_pi_selects_pi() -> None:
    selection = resolve_runtime_policy(
        "auto",
        env={
            "AGENT_RUNTIME": "pi",
            "PI_ENABLED": "true",
            "PI_MODEL": "pi-model",
            "PI_BASE_URL": "http://127.0.0.1:8787",
            "PI_API_KEY": "pi-key",
        },
    )

    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "pi"
    assert selection.fallback_reason == ""
    assert selection.warnings == []


def test_replay_ignores_complete_pi_configuration() -> None:
    selection = resolve_runtime_policy(
        "replay",
        env={
            "AGENT_RUNTIME": "pi",
            "PI_ENABLED": "true",
            "PI_MODEL": "pi-model",
            "PI_BASE_URL": "http://127.0.0.1:8787",
            "PI_API_KEY": "pi-key",
        },
    )

    assert selection.resolved_mode == "replay"
    assert selection.runtime_name == ""


def test_disabled_pi_is_unavailable_with_warning() -> None:
    selection = resolve_runtime_policy(
        "auto",
        env={
            "AGENT_RUNTIME": "pi",
            "PI_ENABLED": "false",
            "LLM_API_KEY": "legacy-key",
        },
    )

    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "PI_ENABLED" in selection.fallback_reason
    assert selection.warnings


def test_incomplete_pi_without_legacy_key_is_live_but_unavailable() -> None:
    selection = resolve_runtime_policy(
        "auto",
        env={"AGENT_RUNTIME": "pi", "PI_ENABLED": "true"},
    )

    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "PI_MODEL" in selection.fallback_reason
    assert selection.warnings


def test_live_incomplete_pi_does_not_fall_back_to_legacy() -> None:
    selection = resolve_runtime_policy(
        "live",
        env={"AGENT_RUNTIME": "pi", "PI_ENABLED": "true", "LLM_API_KEY": "legacy-key"},
    )

    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "PI_MODEL" in selection.fallback_reason
    assert selection.warnings


def test_explicit_mock_runtime_is_unavailable_for_api_modes() -> None:
    selection = resolve_runtime_policy("auto", env={"AGENT_RUNTIME": "mock"})
    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "AGENT_RUNTIME" in selection.fallback_reason


def test_live_without_pi_stays_live_for_explicit_failure() -> None:
    selection = resolve_runtime_policy("live", env={})
    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "AGENT_RUNTIME" in selection.warnings[0]


def test_strict_pi_policy_reports_unavailable_without_pi_config() -> None:
    selection = resolve_runtime_policy(
        "live", env={"AGENT_RUNTIME": "pi"}, require_pi=True
    )
    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "PI_ENABLED" in selection.fallback_reason


def test_unknown_runtime_is_warned_and_not_marked_as_pi_success() -> None:
    selection = resolve_runtime_policy(
        "auto",
        env={"AGENT_RUNTIME": "surprise", "LLM_API_KEY": "test-key"},
    )
    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert selection.runtime_name != "pi"
    assert "surprise" in selection.fallback_reason
    assert selection.warnings


def test_unknown_runtime_without_key_is_live_but_unavailable() -> None:
    selection = resolve_runtime_policy("auto", env={"AGENT_RUNTIME": "surprise"})
    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert "surprise" in selection.fallback_reason
    assert selection.warnings


@pytest.mark.parametrize("api_mode", ["debug", ""])
def test_invalid_api_mode_is_rejected(api_mode: str) -> None:
    with pytest.raises(ValueError):
        resolve_runtime_policy(api_mode, env={})


def test_runtime_policy_does_not_import_fastapi_or_runtime_creation() -> None:
    import app.agent_runtime.runtime_policy as module

    source = inspect.getsource(module)
    for forbidden in ("fastapi", "create_runtime", "LegacyLLMRuntime", "chat("):
        assert forbidden not in source, forbidden
