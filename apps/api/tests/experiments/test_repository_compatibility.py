"""Legacy experiment rows remain readable after P3 provenance is added."""

import json

from app.experiments.repository import ExperimentDatasetRepository
from app.storage.sqlite_store import SQLiteStore


def test_legacy_synthetic_dataset_without_p3_metadata_is_readable(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "legacy.db")
    store.initialize()
    with store.transaction() as connection:
        connection.execute(
            """
            INSERT INTO experiment_datasets
                (dataset_id, version, project_id, group_chat_id, source_document_id,
                 sample_schema_json, units_json, conditions_json, rows_json,
                 data_space, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-dataset",
                1,
                "project-a",
                "group-a",
                "doc-legacy",
                json.dumps({"sample_id": "sample_id", "strength": "number"}),
                json.dumps({"strength": "MPa"}),
                json.dumps({"curing_days": 28}),
                json.dumps([
                    {
                        "row_number": 2,
                        "values": {"sample_id": "S-1", "strength": 3.2},
                        "source_document_id": "doc-legacy",
                        "source_location": "doc-legacy:row:2",
                        "data_space": "synthetic",
                        "source_mode": "fixture",
                        "verification_status": "fixture",
                    }
                ]),
                "synthetic",
                1.0,
                1.0,
            ),
        )

    store.close()
    reopened = SQLiteStore(tmp_path / "legacy.db")
    reopened.initialize()
    dataset = ExperimentDatasetRepository(reopened).get("legacy-dataset", 1)

    assert dataset is not None
    assert dataset.source_mode == "fixture"
    assert dataset.verification_status == "fixture"
    assert dataset.rows[0].source_document_id == "doc-legacy"
