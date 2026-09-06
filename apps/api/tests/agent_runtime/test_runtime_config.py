"""Process-local Runtime configuration must not leak secrets."""

from app.agent_runtime.config import RuntimeConfigStore


def test_runtime_config_status_never_contains_api_key() -> None:
    store = RuntimeConfigStore()

    status = store.configure(
        provider="pi",
        base_url="http://pi.local/invoke",
        model="research-model",
        api_key="secret-value",
    )

    assert status.configured is True
    assert status.provider == "pi"
    assert status.model == "research-model"
    assert "secret-value" not in status.model_dump_json()
    assert "secret-value" not in repr(status)

    store.clear()
    assert store.status().configured is False


def test_runtime_config_rejects_blank_provider_model_and_url() -> None:
    store = RuntimeConfigStore()

    try:
        store.configure(provider="", base_url="http://pi", model="m", api_key="k")
    except ValueError as exc:
        assert "provider" in str(exc)
    else:
        raise AssertionError("blank provider must be rejected")

    try:
        store.configure(provider="pi", base_url="", model="", api_key="k")
    except ValueError as exc:
        assert "model" in str(exc)
    else:
        raise AssertionError("blank model and URL must be rejected")
