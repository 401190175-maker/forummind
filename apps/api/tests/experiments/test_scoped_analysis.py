"""Dataset analysis must use a server-owned group and dataset scope."""

import pytest

from app.experiments.analysis import AnalysisService
from app.experiments.importers import ExperimentImporter
from app.experiments.integration import DatasetScope, ScopedExperimentAnalysis
from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import AnalysisSpec, DatasetImportMetadata
from app.storage.sqlite_store import SQLiteStore


def _analysis(tmp_path):
    store = SQLiteStore(tmp_path / "scoped.db")
    store.initialize()
    repository = ExperimentDatasetRepository(store)
    dataset = ExperimentImporter(repository).import_bytes(
        b"sample_id,strength\nS-1,3.2\nS-2,3.8\n",
        filename="results.csv",
        metadata=DatasetImportMetadata(
            dataset_id="dataset-a", project_id="project-a", group_chat_id="group-a",
            source_document_id="doc-a", data_space="desensitized_real", source_mode="live",
            sample_schema={"sample_id": "sample_id", "strength": "number"},
            units={"strength": "MPa"},
        ),
    )
    return store, dataset, ScopedExperimentAnalysis(AnalysisService(repository))


def test_scoped_analysis_returns_provenance_for_an_authorized_dataset(tmp_path) -> None:
    store, dataset, analysis = _analysis(tmp_path)

    result = analysis.analyze(
        DatasetScope(group_chat_id="group-a", data_space="desensitized_real", dataset_ids=["dataset-a"]),
        "dataset-a", AnalysisSpec(operation="summary", column_name="strength"),
    )

    assert result.data_space == "desensitized_real"
    assert result.provenance[0].source_ref.startswith("dataset:dataset-a:v1:row:")
    store.close()


def test_scoped_analysis_rejects_cross_group_or_unlisted_dataset(tmp_path) -> None:
    store, _dataset, analysis = _analysis(tmp_path)
    spec = AnalysisSpec(operation="summary", column_name="strength")

    with pytest.raises(ValueError, match="dataset scope"):
        analysis.analyze(
            DatasetScope(group_chat_id="group-a", data_space="desensitized_real", dataset_ids=["dataset-b"]),
            "dataset-a", spec,
        )
    with pytest.raises(ValueError, match="group scope"):
        analysis.analyze(
            DatasetScope(group_chat_id="group-b", data_space="desensitized_real", dataset_ids=["dataset-a"]),
            "dataset-a", spec,
        )
    store.close()
