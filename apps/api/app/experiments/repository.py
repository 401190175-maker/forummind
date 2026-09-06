"""SQLite persistence for immutable experiment versions and analyses."""

from __future__ import annotations

from collections.abc import Mapping
import json

from app.experiments.schemas import (
    AnalysisResult,
    ExperimentDataset,
    ExperimentDatasetSummary,
    SourceRowRef,
)
from app.storage.sqlite_store import SQLiteStore


class ExperimentDatasetRepository:
    """Persist only append-only dataset versions and analysis records."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def next_version(self, dataset_id: str) -> int:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM experiment_datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
        return int(row["version"]) + 1

    def save(self, dataset: ExperimentDataset) -> ExperimentDataset:
        with self.store.transaction() as connection:
            self._insert_dataset(connection, dataset)
        return dataset

    def append(self, dataset: ExperimentDataset) -> ExperimentDataset:
        """Append a new immutable version using the durable current maximum."""

        with self.store.transaction() as connection:
            stored = self._append_in_connection(connection, dataset)
        return stored

    def append_with_source(
        self, dataset: ExperimentDataset, *, source_id: str, storage_path: str
    ) -> ExperimentDataset:
        """Append a dataset and its source metadata in one database transaction."""

        with self.store.transaction() as connection:
            stored = self._append_in_connection(connection, dataset)
            self._insert_source(connection, source_id=source_id, dataset=stored, storage_path=storage_path)
        return stored

    def _append_in_connection(self, connection, dataset: ExperimentDataset) -> ExperimentDataset:
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM experiment_datasets WHERE dataset_id = ?",
            (dataset.dataset_id,),
        ).fetchone()
        version = int(row["version"]) + 1
        stored = dataset if dataset.version == version else dataset.model_copy(update={"version": version})
        self._insert_dataset(connection, stored)
        return stored

    @staticmethod
    def _insert_dataset(connection, dataset: ExperimentDataset) -> None:
        provenance = {
            "filename": dataset.filename,
            "source_sha256": dataset.source_sha256,
            "source_mode": dataset.source_mode,
            "verification_status": dataset.verification_status,
        }
        connection.execute(
            """
            INSERT INTO experiment_datasets
                (dataset_id, version, project_id, group_chat_id, source_document_id,
                 sample_schema_json, units_json, conditions_json, rows_json,
                 data_space, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset.dataset_id,
                dataset.version,
                dataset.project_id,
                dataset.group_chat_id,
                dataset.source_document_id,
                _dump(dataset.sample_schema),
                _dump(dataset.units),
                _dump({"conditions": dataset.conditions, "__p3_provenance__": provenance}),
                _dump([row.model_dump(mode="json") for row in dataset.rows]),
                dataset.data_space,
                dataset.created_at,
                dataset.updated_at,
            )
        )

    def get(self, dataset_id: str, version: int) -> ExperimentDataset | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT * FROM experiment_datasets WHERE dataset_id = ? AND version = ?",
                (dataset_id, version),
            ).fetchone()
        return None if row is None else _dataset_from_row(row)

    def latest(self, dataset_id: str, *, group_chat_id: str | None = None) -> ExperimentDataset | None:
        statement = "SELECT * FROM experiment_datasets WHERE dataset_id = ?"
        parameters: list[object] = [dataset_id]
        if group_chat_id is not None:
            statement += " AND group_chat_id = ?"
            parameters.append(group_chat_id)
        statement += " ORDER BY version DESC LIMIT 1"
        with self.store.locked() as connection:
            row = connection.execute(statement, parameters).fetchone()
        return None if row is None else _dataset_from_row(row)

    def list_versions(self, dataset_id: str, *, group_chat_id: str | None = None) -> list[ExperimentDataset]:
        statement = "SELECT * FROM experiment_datasets WHERE dataset_id = ?"
        parameters: list[object] = [dataset_id]
        if group_chat_id is not None:
            statement += " AND group_chat_id = ?"
            parameters.append(group_chat_id)
        statement += " ORDER BY version, dataset_id"
        with self.store.locked() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [_dataset_from_row(row) for row in rows]

    def list_summaries(self, group_chat_id: str) -> list[ExperimentDatasetSummary]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM (
                    SELECT d.*, ROW_NUMBER() OVER (
                        PARTITION BY dataset_id ORDER BY version DESC
                    ) AS row_number
                    FROM experiment_datasets d
                    WHERE group_chat_id = ?
                )
                WHERE row_number = 1
                ORDER BY dataset_id
                """,
                (group_chat_id,),
            ).fetchall()
        summaries: list[ExperimentDatasetSummary] = []
        for row in rows:
            # filename and hash are kept in the version's conditions payload for
            # compatibility with the original experiment_datasets schema.
            dataset = _dataset_from_row(row)
            summaries.append(ExperimentDatasetSummary(
                dataset_id=dataset.dataset_id,
                latest_version=dataset.version,
                filename=dataset.filename,
                source_sha256=dataset.source_sha256,
                row_count=len(dataset.rows),
                columns=list(dataset.sample_schema),
                created_at=dataset.created_at,
                updated_at=dataset.updated_at,
            ))
        return summaries

    def list_analyses(
        self, dataset_id: str, version: int, *, group_chat_id: str,
    ) -> list[AnalysisResult]:
        dataset = self.get(dataset_id, version)
        if dataset is None or dataset.group_chat_id != group_chat_id:
            return []
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT * FROM experiment_analysis
                WHERE dataset_id = ? AND dataset_version = ?
                ORDER BY created_at, analysis_id
                """,
                (dataset_id, version),
            ).fetchall()
        return [_analysis_from_row(row) for row in rows]

    def save_source(
        self, *, source_id: str, dataset: ExperimentDataset, storage_path: str,
    ) -> None:
        with self.store.transaction() as connection:
            self._insert_source(connection, source_id=source_id, dataset=dataset, storage_path=storage_path)

    @staticmethod
    def _insert_source(connection, *, source_id: str, dataset: ExperimentDataset, storage_path: str) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO experiment_source_files
                (source_id, dataset_id, dataset_version, group_chat_id,
                 filename, source_sha256, storage_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id, dataset.dataset_id, dataset.version,
                dataset.group_chat_id, dataset.filename, dataset.source_sha256,
                storage_path, dataset.created_at,
            ),
        )

    def get_source(self, dataset_id: str, version: int, *, group_chat_id: str) -> dict | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM experiment_source_files
                WHERE dataset_id = ? AND dataset_version = ? AND group_chat_id = ?
                """,
                (dataset_id, version, group_chat_id),
            ).fetchone()
        return None if row is None else dict(row)

    def save_analysis(self, result: AnalysisResult) -> AnalysisResult:
        provenance = {
            "refs": [ref.model_dump(mode="json") for ref in result.provenance],
            "source_mode": result.source_mode,
            "causal_interpretation_allowed": result.causal_interpretation_allowed,
            "warnings": result.warnings,
        }
        with self.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO experiment_analysis
                    (analysis_id, dataset_id, dataset_version, operation, column_name,
                     result_json, input_refs_json, output_refs_json, provenance_json,
                     data_space, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.analysis_id,
                    result.dataset_id,
                    result.dataset_version,
                    result.operation,
                    result.column_name,
                    _dump(result.result),
                    _dump([ref.model_dump(mode="json") for ref in result.input_refs]),
                    _dump(result.output_refs),
                    _dump(provenance),
                    result.data_space,
                    result.created_at,
                ),
            )
        return result

    def get_analysis(self, analysis_id: str) -> AnalysisResult | None:
        with self.store.locked() as connection:
            row = connection.execute(
                "SELECT * FROM experiment_analysis WHERE analysis_id = ?", (analysis_id,)
            ).fetchone()
        if row is None:
            return None
        return _analysis_from_row(row)


def _analysis_from_row(row: Mapping[str, object]) -> AnalysisResult:
    provenance = json.loads(row["provenance_json"])
    refs = [SourceRowRef.model_validate(item) for item in json.loads(row["input_refs_json"])]
    return AnalysisResult(
            analysis_id=row["analysis_id"],
            dataset_id=row["dataset_id"],
            dataset_version=row["dataset_version"],
            operation=row["operation"],
            column_name=row["column_name"],
            result=json.loads(row["result_json"]),
            input_refs=refs,
            output_refs=json.loads(row["output_refs_json"]),
            provenance=[SourceRowRef.model_validate(item) for item in provenance.get("refs", [])],
            data_space=row["data_space"],
            source_mode=provenance.get("source_mode", "live"),
            causal_interpretation_allowed=False,
            warnings=provenance.get("warnings", []),
            created_at=row["created_at"],
    )


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dataset_from_row(row: Mapping[str, object]) -> ExperimentDataset:
    conditions_payload = json.loads(row["conditions_json"])
    provenance = conditions_payload.get("__p3_provenance__", {})
    conditions = conditions_payload.get("conditions", conditions_payload)
    data_space = row["data_space"]
    legacy_fixture = not provenance and data_space == "synthetic"
    return ExperimentDataset(
        dataset_id=row["dataset_id"],
        version=row["version"],
        project_id=row["project_id"],
        group_chat_id=row["group_chat_id"],
        source_document_id=row["source_document_id"],
        filename=provenance.get("filename", "source.csv"),
        source_sha256=provenance.get("source_sha256", "0" * 64),
        sample_schema=json.loads(row["sample_schema_json"]),
        units=json.loads(row["units_json"]),
        conditions=conditions,
        rows=json.loads(row["rows_json"]),
        data_space=data_space,
        source_mode=provenance.get("source_mode", "fixture" if legacy_fixture else "live"),
        verification_status=provenance.get("verification_status", "fixture" if legacy_fixture else "unverified"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
