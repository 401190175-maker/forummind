"""Application-level registration for the independent P3 experiment API."""

import app.main as main_module
from app.api import experiments as experiments_api


def test_main_registers_experiment_dataset_routes() -> None:
    paths = main_module.app.openapi()["paths"]

    assert "/group-chats/{group_chat_id}/experiment-datasets" in paths
    assert "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions" in paths
    assert "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analysis" in paths


def test_application_persistence_configures_experiment_api(monkeypatch) -> None:
    configured_stores = []

    def capture_store(store, *, source_root=None) -> None:
        configured_stores.append((store, source_root))

    monkeypatch.setattr(experiments_api, "configure_persistence", capture_store)

    main_module.configure_application_persistence()

    assert configured_stores == [(main_module.app_store, main_module.resolve_experiment_source_root())]
