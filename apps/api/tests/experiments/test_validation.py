"""Experiment schema, unit and sample validation contracts."""

import importlib.util

import pytest

from app.experiments.schemas import ExperimentDataset, ExperimentRow
from app.experiments.validation import DatasetValidationError, validate_rows


def test_experiment_validation_module_exposes_the_p3_boundary():
    try:
        module = importlib.util.find_spec("app.experiments.validation")
    except ModuleNotFoundError:
        module = None

    assert module is not None


_SCHEMA = {"sample_id": "sample_id", "density": "number", "strength": "number"}


def _validate(rows, *, units=None, data_space="desensitized_real", source_mode="live"):
    return validate_rows(
        ["sample_id", "density", "strength"], rows, _SCHEMA,
        units if units is not None else {"density": "kg/m3", "strength": "MPa"},
        source_document_id="doc-exp-1", data_space=data_space, source_mode=source_mode,
    )


def test_validation_rejects_missing_units_before_numeric_analysis():
    with pytest.raises(DatasetValidationError, match="missing unit") as error:
        _validate([["S-1", "600", "3.2"]], units={"density": "kg/m3"})

    assert error.value.column_name == "strength"
    assert error.value.code == "missing_unit"


def test_validation_rejects_duplicate_sample_ids_with_row_location():
    with pytest.raises(DatasetValidationError, match="duplicate sample") as error:
        _validate([["S-1", "600", "3.2"], ["S-1", "610", "3.4"]])

    assert error.value.row_number == 3
    assert error.value.column_name == "sample_id"


def test_validation_rejects_invalid_numeric_values_and_unknown_units():
    with pytest.raises(DatasetValidationError) as invalid_value:
        _validate([["S-1", "not-a-number", "3.2"]])
    assert invalid_value.value.code == "invalid_number"
    assert invalid_value.value.row_number == 2
    assert invalid_value.value.column_name == "density"

    with pytest.raises(DatasetValidationError, match="unsupported unit"):
        _validate([["S-1", "600", "3.2"]], units={"density": "made-up", "strength": "MPa"})


def test_fixture_rows_keep_synthetic_origin_and_fixture_verification_status():
    rows = _validate(
        [["S-1", "600", "3.2"]], data_space="synthetic", source_mode="fixture"
    )

    assert rows[0].data_space == "synthetic"
    assert rows[0].source_mode == "fixture"
    assert rows[0].verification_status == "fixture"


def test_dataset_rejects_row_origin_that_does_not_match_dataset():
    with pytest.raises(ValueError, match="fixture provenance"):
        ExperimentDataset(
            dataset_id="dataset-1", version=1, project_id="project-a", group_chat_id="group-a",
            source_document_id="doc-1", filename="results.csv", source_sha256="a" * 64,
            sample_schema={"sample_id": "sample_id"}, units={}, conditions={},
            rows=[ExperimentRow(
                row_number=2, values={"sample_id": "S-1"}, source_document_id="doc-1",
                source_location="doc-1:row:2", data_space="desensitized_real",
                source_mode="fixture", verification_status="fixture",
            )], data_space="desensitized_real", source_mode="live",
            verification_status="verified", created_at=1.0, updated_at=1.0,
        )


def test_experiment_row_rejects_fixture_status_in_a_real_data_space():
    with pytest.raises(ValueError, match="fixture provenance"):
        ExperimentRow(
            row_number=2, values={"sample_id": "S-1"}, source_document_id="doc-1",
            source_location="doc-1:row:2", data_space="desensitized_real",
            source_mode="fixture", verification_status="fixture",
        )


def test_validation_rejects_unknown_sample_field_types():
    with pytest.raises(DatasetValidationError, match="unsupported field type") as error:
        validate_rows(
            ["sample_id", "strength"], [["S-1", "3.2"]],
            {"sample_id": "sample_id", "strength": "formula"},
            {"strength": "MPa"}, source_document_id="doc-1",
            data_space="desensitized_real", source_mode="live",
        )

    assert error.value.code == "invalid_schema"
