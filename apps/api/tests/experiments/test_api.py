"""Independent experiment API router contracts."""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.experiments import configure_persistence, router
from app.storage.sqlite_store import SQLiteStore


def _client(tmp_path):
    store = SQLiteStore(tmp_path / "api.db")
    store.initialize()
    with store.transaction() as connection:
        connection.execute(
            """
            INSERT INTO group_chats
                (group_chat_id, data_space, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("group-a", "desensitized_real", json.dumps({}), 1.0, 1.0),
        )
    configure_persistence(store, source_root=tmp_path / "sources")
    application = FastAPI()
    application.include_router(router)
    return TestClient(application)


_FORM = {
    "project_id": "project-a",
    "source_document_id": "doc-exp-api",
    "data_space": "desensitized_real",
    "source_mode": "live",
    "sample_schema": '{"sample_id":"sample_id","strength":"number"}',
    "units": '{"strength":"MPa"}',
    "conditions": '{"curing_days":28}',
    "dataset_id": "dataset-api",
}


def test_experiment_api_imports_versions_lists_them_and_analyzes(tmp_path):
    client = _client(tmp_path)
    first = client.post(
        "/group-chats/group-a/experiment-datasets",
        data=_FORM,
        files={"file": ("results.csv", b"sample_id,strength\nS-1,3.2\nS-2,3.8\n", "text/csv")},
    )
    second = client.post(
        "/group-chats/group-a/experiment-datasets",
        data=_FORM,
        files={"file": ("results-v2.csv", b"sample_id,strength\nS-1,3.4\nS-2,4.0\n", "text/csv")},
    )

    assert first.status_code == 201
    assert first.json()["version"] == 1
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert client.get("/group-chats/group-a/experiment-datasets/dataset-api/versions").json()[1]["version"] == 2

    analysis = client.post(
        "/group-chats/group-a/experiment-datasets/dataset-api/analysis",
        json={"operation": "summary", "column_name": "strength"},
    )

    assert analysis.status_code == 201
    assert analysis.json()["result"]["mean"] == 3.7
    assert analysis.json()["causal_interpretation_allowed"] is False
    assert analysis.json()["input_refs"][0]["source_document_id"].startswith("experiment-source-")


def test_experiment_api_rejects_non_object_metadata_json(tmp_path):
    client = _client(tmp_path)
    form = dict(_FORM)
    form["sample_schema"] = "[]"

    response = client.post(
        "/group-chats/group-a/experiment-datasets",
        data=form,
        files={"file": ("results.csv", b"sample_id,strength\nS-1,3.2\n", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "sample_schema must be a JSON object"
