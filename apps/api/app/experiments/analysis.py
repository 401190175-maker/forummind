"""Whitelisted experiment analysis with row-level provenance."""

from __future__ import annotations

import math
from time import time
from uuid import uuid4

from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import AnalysisResult, AnalysisSpec, ExperimentDataset, SourceRowRef


class AnalysisError(ValueError):
    """The requested analysis is unsafe or incompatible with the dataset."""


class AnalysisService:
    """Run small, deterministic analyses without evaluating model-supplied code."""

    def __init__(self, repository: ExperimentDatasetRepository) -> None:
        self.repository = repository

    def analyze_dataset(
        self,
        dataset_id: str,
        analysis_spec: AnalysisSpec,
        *,
        version: int | None = None,
        group_chat_id: str | None = None,
    ) -> AnalysisResult:
        dataset = (
            self.repository.get(dataset_id, version)
            if version is not None
            else self.repository.latest(dataset_id, group_chat_id=group_chat_id)
        )
        if dataset is None:
            raise KeyError(dataset_id)
        if group_chat_id is not None and dataset.group_chat_id != group_chat_id:
            raise AnalysisError("dataset group scope denied")
        self._require_numeric(dataset, analysis_spec.column_name)
        columns = [analysis_spec.column_name]
        if analysis_spec.operation == "summary":
            result = self._summary(dataset, analysis_spec.column_name)
            warnings: list[str] = []
        elif analysis_spec.operation == "correlation":
            compare = analysis_spec.compare_column
            if not compare:
                raise AnalysisError("correlation requires compare_column")
            self._require_numeric(dataset, compare)
            columns.append(compare)
            result = self._correlation(dataset, analysis_spec.column_name, compare)
            warnings = ["correlation_not_causation"]
        elif analysis_spec.operation == "group_mean":
            if not analysis_spec.group_by:
                raise AnalysisError("group_mean requires group_by")
            self._require_column(dataset, analysis_spec.group_by)
            columns.append(analysis_spec.group_by)
            result = self._group_mean(dataset, analysis_spec.column_name, analysis_spec.group_by)
            warnings = []
        else:
            raise AnalysisError("unsupported analysis operation")

        analysis_id = f"analysis-{uuid4().hex}"
        refs = [self._row_ref(dataset, row, column) for row in dataset.rows for column in columns]
        analysis = AnalysisResult(
            analysis_id=analysis_id,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            operation=analysis_spec.operation,
            column_name=analysis_spec.column_name,
            result=result,
            input_refs=refs,
            output_refs=[f"analysis:{analysis_id}"],
            provenance=refs,
            data_space=dataset.data_space,
            source_mode=dataset.source_mode,
            causal_interpretation_allowed=False,
            warnings=warnings,
            created_at=time(),
        )
        return self.repository.save_analysis(analysis)

    @staticmethod
    def _require_column(dataset: ExperimentDataset, column: str) -> None:
        if column not in dataset.sample_schema:
            raise AnalysisError(f"unknown analysis column: {column}")

    @classmethod
    def _require_numeric(cls, dataset: ExperimentDataset, column: str) -> None:
        cls._require_column(dataset, column)
        if dataset.sample_schema[column] != "number":
            raise AnalysisError(f"analysis column is not numeric: {column}")

    @staticmethod
    def _values(dataset: ExperimentDataset, column: str) -> list[float]:
        return [float(row.values[column]) for row in dataset.rows]

    def _summary(self, dataset: ExperimentDataset, column: str) -> dict[str, float | int]:
        values = self._values(dataset, column)
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": _stable_mean(values),
        }

    def _correlation(self, dataset: ExperimentDataset, left_column: str, right_column: str) -> dict[str, float | int | None]:
        left = self._values(dataset, left_column)
        right = self._values(dataset, right_column)
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
        denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
        return {"count": len(left), "coefficient": None if denominator == 0 else numerator / denominator}

    def _group_mean(self, dataset: ExperimentDataset, value_column: str, group_column: str) -> dict[str, dict[str, float | int]]:
        groups: dict[str, list[float]] = {}
        for row in dataset.rows:
            key = str(row.values[group_column])
            groups.setdefault(key, []).append(float(row.values[value_column]))
        return {
            key: {"count": len(values), "mean": _stable_mean(values)}
            for key, values in sorted(groups.items())
        }

    @staticmethod
    def _row_ref(dataset: ExperimentDataset, row, column: str) -> SourceRowRef:
        return SourceRowRef(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            source_document_id=row.source_document_id,
            row_number=row.row_number,
            column_name=column,
            source_location=row.source_location,
            data_space=row.data_space,
            verification_status=row.verification_status,
            source_ref=f"dataset:{dataset.dataset_id}:v{dataset.version}:row:{row.row_number}:column:{column}",
        )


def _stable_mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 12)
