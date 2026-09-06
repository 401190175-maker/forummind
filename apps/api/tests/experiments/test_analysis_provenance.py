"""Safe analysis and source-row provenance contracts."""

import importlib.util

import pytest

from app.experiments.analysis import AnalysisService
from app.experiments.importers import ExperimentImporter
from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import AnalysisResult, AnalysisSpec, DatasetImportMetadata
from app.storage.sqlite_store import SQLiteStore


def test_experiment_analysis_module_exposes_the_p3_boundary():
    try:
        module = importlib.util.find_spec("app.experiments.analysis")
    except ModuleNotFoundError:
        module = None

    assert module is not None


def _dataset(tmp_path):
    store = SQLiteStore(tmp_path / "analysis.db")
    store.initialize()
    repository = ExperimentDatasetRepository(store)
    dataset = ExperimentImporter(repository).import_bytes(
        b"sample_id,density,strength\nS-1,600,3.2\nS-2,650,3.8\nS-3,700,4.4\n",
        filename="results.csv",
        metadata=DatasetImportMetadata(
            dataset_id="dataset-analysis", project_id="project-a", group_chat_id="group-a",
            source_document_id="doc-exp-1", data_space="desensitized_real", source_mode="live",
            sample_schema={"sample_id": "sample_id", "density": "number", "strength": "number"},
            units={"density": "kg/m3", "strength": "MPa"}, conditions={"curing_days": 28},
        ),
    )
    return store, repository, dataset


def test_summary_analysis_returns_source_row_refs_and_persists_after_restart(tmp_path):
    store, repository, dataset = _dataset(tmp_path)
    result = AnalysisService(repository).analyze_dataset(
        dataset.dataset_id, AnalysisSpec(operation="summary", column_name="strength")
    )
    store.close()

    reopened = SQLiteStore(tmp_path / "analysis.db")
    reopened.initialize()
    saved = ExperimentDatasetRepository(reopened).get_analysis(result.analysis_id)

    assert result.result == {"count": 3, "min": 3.2, "max": 4.4, "mean": 3.8}
    assert len(result.input_refs) == 3
    assert {ref.source_location for ref in result.input_refs} == {
        "doc-exp-1:row:2", "doc-exp-1:row:3", "doc-exp-1:row:4"
    }
    assert all(ref.column_name == "strength" for ref in result.input_refs)
    assert result.output_refs == [f"analysis:{result.analysis_id}"]
    assert saved is not None
    assert saved.input_refs == result.input_refs


def test_correlation_analysis_is_explicitly_non_causal(tmp_path):
    _store, repository, dataset = _dataset(tmp_path)

    result = AnalysisService(repository).analyze_dataset(
        dataset.dataset_id,
        AnalysisSpec(operation="correlation", column_name="density", compare_column="strength"),
    )

    assert result.result["coefficient"] > 0.99
    assert result.causal_interpretation_allowed is False
    assert "correlation_not_causation" in result.warnings
    assert {ref.column_name for ref in result.input_refs} == {"density", "strength"}


def test_analysis_result_rejects_a_same_space_reference_from_another_dataset(tmp_path):
    _store, repository, dataset = _dataset(tmp_path)
    result = AnalysisService(repository).analyze_dataset(
        dataset.dataset_id, AnalysisSpec(operation="summary", column_name="strength")
    )
    foreign_ref = result.input_refs[0].model_copy(update={"dataset_id": "other-dataset"})

    with pytest.raises(ValueError, match="dataset provenance"):
        AnalysisResult.model_validate(result.model_copy(update={
            "input_refs": [foreign_ref], "provenance": [foreign_ref],
        }))
