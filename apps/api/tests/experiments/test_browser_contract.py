from __future__ import annotations

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
    return TestClient(application), store


def test_preview_is_read_only_and_returns_browser_contract(tmp_path):
    client, store = _client(tmp_path)
    before = store.connection().execute("SELECT COUNT(*) AS count FROM experiment_datasets").fetchone()["count"]

    response = client.post(
        "/group-chats/group-a/experiment-datasets/preview",
        files={"file": ("results.csv", b"sample_id,strength\nS-1,3.2\nS-2,3.8\n", "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["sample_id", "strength"]
    assert body["inferred_field_types"]["strength"] == "number"
    assert body["sample_rows"][0]["sample_id"] == "S-1"
    assert isinstance(body["validation_findings"], list)
    after = store.connection().execute("SELECT COUNT(*) AS count FROM experiment_datasets").fetchone()["count"]
    assert after == before == 0


def test_list_history_and_source_routes_expose_persisted_import(tmp_path):
    client, store = _client(tmp_path)
    form = {
        "project_id": "spoofed-project",
        "source_document_id": "spoofed-document",
        "data_space": "synthetic",
        "source_mode": "live",
        "sample_schema": '{"sample_id":"sample_id","strength":"number"}',
        "dataset_id": "dataset-browser",
    }
    imported = client.post(
        "/group-chats/group-a/experiment-datasets",
        data=form,
        files={"file": ("results.csv", b"sample_id,strength\nS-1,3.2\nS-2,3.8\n", "text/csv")},
    )

    assert imported.status_code == 201
    dataset = imported.json()
    assert dataset["project_id"] == "group-project:group-a"
    assert dataset["data_space"] == "desensitized_real"
    assert dataset["source_document_id"].startswith("experiment-source-")

    summaries = client.get("/group-chats/group-a/experiment-datasets")
    assert summaries.status_code == 200
    assert summaries.json()[0] == {
        "dataset_id": "dataset-browser",
        "latest_version": 1,
        "filename": "results.csv",
        "source_sha256": dataset["source_sha256"],
        "row_count": 2,
        "columns": ["sample_id", "strength"],
        "created_at": dataset["created_at"],
        "updated_at": dataset["updated_at"],
    }

    history = client.get(
        "/group-chats/group-a/experiment-datasets/dataset-browser/analyses?version=1"
    )
    assert history.status_code == 200
    assert history.json() == []

    source = client.get(
        "/group-chats/group-a/experiment-datasets/dataset-browser/versions/1/source"
    )
    assert source.status_code == 200
    assert source.content.startswith(b"sample_id,strength")

    cross_group = client.get(
        "/group-chats/other-group/experiment-datasets/dataset-browser/versions/1/source"
    )
    assert cross_group.status_code == 404
    store.close()


def test_preview_rejects_unsupported_file_and_malformed_rows(tmp_path):
    client, store = _client(tmp_path)
    unsupported = client.post(
        "/group-chats/group-a/experiment-datasets/preview",
        files={"file": ("notes.txt", b"not a table", "text/plain")},
    )
    malformed = client.post(
        "/group-chats/group-a/experiment-datasets/preview",
        files={"file": ("results.csv", b"sample_id,strength\nS-1\n", "text/csv")},
    )

    assert unsupported.status_code == 422
    assert malformed.status_code == 200
    assert malformed.json()["validation_findings"]
    store.close()


def test_import_rejects_unknown_group_even_with_caller_metadata(tmp_path):
    client, store = _client(tmp_path)
    response = client.post(
        "/group-chats/missing-group/experiment-datasets",
        data={
            "project_id": "caller-project",
            "source_document_id": "caller-source",
            "data_space": "desensitized_real",
            "source_mode": "live",
            "sample_schema": '{"sample_id":"sample_id","strength":"number"}',
        },
        files={"file": ("results.csv", b"sample_id,strength\nS-1,3.2\n", "text/csv")},
    )

    assert response.status_code == 404
    store.close()


def test_import_rejects_reusing_dataset_id_owned_by_another_group(tmp_path):
    client, store = _client(tmp_path)
    with store.transaction() as connection:
        connection.execute(
            """
            INSERT INTO group_chats
                (group_chat_id, data_space, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("group-b", "desensitized_real", json.dumps({}), 1.0, 1.0),
        )
    form = {
        "sample_schema": '{"sample_id":"sample_id","strength":"number"}',
        "dataset_id": "foreign-dataset",
    }
    first = client.post(
        "/group-chats/group-a/experiment-datasets",
        data=form,
        files={"file": ("results.csv", b"sample_id,strength\nS-1,3.2\n", "text/csv")},
    )
    assert first.status_code == 201

    second = client.post(
        "/group-chats/group-b/experiment-datasets",
        data=form,
        files={"file": ("results.csv", b"sample_id,strength\nS-2,3.8\n", "text/csv")},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "dataset_id belongs to another group"
    store.close()
