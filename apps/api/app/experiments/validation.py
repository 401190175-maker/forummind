"""Schema, unit, sample and value validation for imported datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from app.experiments.schemas import DataOrigin, ExperimentRow, SampleFieldType


UNIT_ALIASES = {
    "mpa": "MPa",
    "kpa": "kPa",
    "pa": "Pa",
    "kg/m3": "kg/m3",
    "kg/m^3": "kg/m3",
    "g/cm3": "g/cm3",
    "mm": "mm",
    "cm": "cm",
    "m": "m",
    "s": "s",
    "min": "min",
    "h": "h",
    "c": "C",
    "°c": "C",
    "%": "%",
    "percent": "%",
    "g": "g",
    "kg": "kg",
    "ml": "mL",
    "l": "L",
    "unitless": "unitless",
}


class DatasetValidationError(ValueError):
    """A dataset field cannot be safely interpreted."""

    def __init__(self, message: str, *, code: str, row_number: int | None = None, column_name: str | None = None):
        super().__init__(message)
        self.code = code
        self.row_number = row_number
        self.column_name = column_name


def normalize_unit(value: str, *, column_name: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in UNIT_ALIASES:
        raise DatasetValidationError(
            f"unsupported unit for {column_name}: {value}", code="unsupported_unit", column_name=column_name
        )
    return UNIT_ALIASES[normalized]


def validate_rows(
    headers: Sequence[str],
    raw_rows: Sequence[Sequence[object] | Mapping[str, object]],
    sample_schema: Mapping[str, SampleFieldType],
    units: Mapping[str, str],
    *,
    source_document_id: str,
    data_space: str,
    source_mode: DataOrigin,
) -> list[ExperimentRow]:
    normalized_headers = [str(header).strip() for header in headers]
    if not normalized_headers or any(not header for header in normalized_headers):
        raise DatasetValidationError("column names must be non-empty", code="invalid_schema")
    if len(set(normalized_headers)) != len(normalized_headers):
        raise DatasetValidationError("column names must be unique", code="invalid_schema")
    schema = {str(key).strip(): value for key, value in sample_schema.items()}
    if set(schema) != set(normalized_headers):
        raise DatasetValidationError("sample schema must match the imported columns", code="schema_mismatch")
    if any(kind not in {"sample_id", "number", "text"} for kind in schema.values()):
        raise DatasetValidationError("unsupported field type in sample schema", code="invalid_schema")
    sample_columns = [key for key, kind in schema.items() if kind == "sample_id"]
    if len(sample_columns) != 1:
        raise DatasetValidationError("exactly one sample_id column is required", code="sample_id_schema")
    numeric_columns = [key for key, kind in schema.items() if kind == "number"]
    normalized_units = {str(key).strip(): str(value).strip() for key, value in units.items()}
    for column in numeric_columns:
        if not normalized_units.get(column):
            raise DatasetValidationError(
                f"missing unit for {column}", code="missing_unit", column_name=column
            )
        normalized_units[column] = normalize_unit(normalized_units[column], column_name=column)
    if source_mode in {"fixture", "replay"} and data_space != "synthetic":
        raise DatasetValidationError("fixture and replay rows must remain synthetic", code="origin_mismatch")
    if source_mode == "live" and data_space == "synthetic":
        raise DatasetValidationError("live rows cannot use synthetic data space", code="origin_mismatch")

    sample_column = sample_columns[0]
    seen_samples: set[str] = set()
    validated: list[ExperimentRow] = []
    for offset, raw_row in enumerate(raw_rows, start=2):
        if isinstance(raw_row, Mapping):
            values = {header: raw_row.get(header) for header in normalized_headers}
        else:
            if len(raw_row) != len(normalized_headers):
                raise DatasetValidationError(
                    "row has a different number of values than the header",
                    code="column_count", row_number=offset,
                )
            values = dict(zip(normalized_headers, raw_row))
        sample_value = str(values.get(sample_column, "")).strip()
        if not sample_value:
            raise DatasetValidationError(
                "sample id must be non-empty", code="missing_sample_id",
                row_number=offset, column_name=sample_column,
            )
        if sample_value in seen_samples:
            raise DatasetValidationError(
                f"duplicate sample id: {sample_value}", code="duplicate_sample_id",
                row_number=offset, column_name=sample_column,
            )
        seen_samples.add(sample_value)
        converted: dict[str, object] = {}
        for column, kind in schema.items():
            value = values.get(column)
            if kind == "sample_id":
                converted[column] = sample_value
            elif kind == "number":
                try:
                    number = float(str(value).strip())
                except (TypeError, ValueError) as exc:
                    raise DatasetValidationError(
                        f"invalid number in {column}", code="invalid_number",
                        row_number=offset, column_name=column,
                    ) from exc
                if not math.isfinite(number):
                    raise DatasetValidationError(
                        f"invalid number in {column}", code="invalid_number",
                        row_number=offset, column_name=column,
                    )
                converted[column] = number
            else:
                text = "" if value is None else str(value).strip()
                if not text:
                    raise DatasetValidationError(
                        f"text value is empty in {column}", code="missing_value",
                        row_number=offset, column_name=column,
                    )
                converted[column] = text
        validated.append(ExperimentRow(
            row_number=offset,
            values=converted,
            source_document_id=source_document_id,
            source_location=f"{source_document_id}:row:{offset}",
            data_space=data_space,
            source_mode=source_mode,
            verification_status="fixture" if source_mode in {"fixture", "replay"} else "verified",
        ))
    if not validated:
        raise DatasetValidationError("dataset must contain at least one data row", code="empty_dataset")
    return validated
