from app.agent_runtime.runtime_policy import resolve_runtime_policy


def test_unconfigured_live_mode_is_failed_runtime_selection_not_replay() -> None:
    selection = resolve_runtime_policy(
        "live",
        {
            "AGENT_RUNTIME": "pi",
            "PI_ENABLED": "true",
            "PI_MODEL": "qwen-plus",
        },
        require_pi=True,
    )

    assert selection.resolved_mode == "live"
    assert selection.runtime_name == "unavailable"
    assert selection.fallback_reason
    assert selection.resolved_mode != "replay"
