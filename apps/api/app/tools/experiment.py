"""Task-scoped Live adapter for persisted experiment analyses."""

from __future__ import annotations

from typing import Any

from app.experiments.analysis import AnalysisError, AnalysisService
from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import AnalysisSpec
from app.tasks.schemas import DatasetVersionRef
from app.tools.errors import ToolArgumentsError, ToolScopeError
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest, ToolResult, ToolSpec


_ALLOWED_ARGUMENTS = {
    "dataset_id", "dataset_version", "operation", "column_name", "compare_column", "group_by",
}
_OPERATIONS = {"summary", "correlation", "group_mean"}


def experiment_analyze(request: ToolRequest, context, repository: ExperimentDatasetRepository) -> ToolResult:
    unknown = set(request.arguments) - _ALLOWED_ARGUMENTS
    if unknown:
        raise ToolArgumentsError(f"unsupported arguments: {sorted(unknown)}")
    args = request.arguments
    dataset_id = args.get("dataset_id")
    version = args.get("dataset_version")
    operation = args.get("operation")
    column_name = args.get("column_name")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ToolArgumentsError("dataset_id is required")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ToolArgumentsError("dataset_version must be a positive integer")
    if operation not in _OPERATIONS:
        raise ToolArgumentsError("operation is unsupported")
    if not isinstance(column_name, str) or not column_name.strip():
        raise ToolArgumentsError("column_name is required")
    requested_ref = DatasetVersionRef(dataset_id=dataset_id.strip(), version=version)
    if requested_ref not in context.allowed_dataset_refs:
        raise ToolScopeError("dataset_scope_denied")
    compare = args.get("compare_column")
    group_by = args.get("group_by")
    if compare is not None and (not isinstance(compare, str) or not compare.strip()):
        raise ToolArgumentsError("compare_column must be non-empty text")
    if group_by is not None and (not isinstance(group_by, str) or not group_by.strip()):
        raise ToolArgumentsError("group_by must be non-empty text")
    try:
        result = AnalysisService(repository).analyze_dataset(
            requested_ref.dataset_id,
            AnalysisSpec(
                operation=operation,
                column_name=column_name.strip(),
                compare_column=compare.strip() if isinstance(compare, str) else None,
                group_by=group_by.strip() if isinstance(group_by, str) else None,
            ),
            version=requested_ref.version,
            group_chat_id=context.group_chat_id,
        )
    except KeyError as exc:
        raise ToolScopeError("dataset_scope_denied") from exc
    except AnalysisError as exc:
        raise ToolArgumentsError(str(exc)) from exc
    bounded_refs = [ref.model_dump(mode="json") for ref in result.provenance[:context.limits.max_items]]
    payload: dict[str, Any] = {
        "analysis_id": result.analysis_id,
        "dataset_id": result.dataset_id,
        "dataset_version": result.dataset_version,
        "operation": result.operation,
        "column_name": result.column_name,
        "result": result.result,
        "provenance": bounded_refs,
        "causal_interpretation_allowed": False,
        "warnings": result.warnings,
        "read_only": True,
    }
    return ToolResult(
        request_id=request.request_id,
        name=request.name,
        version="1.0",
        payload=payload,
        source_refs=[f"analysis:{result.analysis_id}"],
        data_space=result.data_space,
        boundary_notes=["read-only", result.data_space, "task-dataset-scope", "candidate-context-only"],
    )


def experiment_spec() -> ToolSpec:
    return ToolSpec(
        name="experiment.analyze",
        version="1.0",
        description="Analyze one immutable experiment dataset version bound to the current task",
        read_only=True,
        input_schema={
            "type": "object",
            "required": ["dataset_id", "dataset_version", "operation", "column_name"],
            "properties": {
                "dataset_id": {"type": "string"},
                "dataset_version": {"type": "integer", "minimum": 1},
                "operation": {"enum": sorted(_OPERATIONS)},
                "column_name": {"type": "string"},
                "compare_column": {"type": "string"},
                "group_by": {"type": "string"},
            },
        },
        output_schema={"type": "object", "properties": {"analysis_id": {"type": "string"}}},
        allowed_roles=["master_student", "phd_student", "postdoc"],
        allowed_phases=["independent_analysis", "review_gate"],
        data_spaces=["real", "desensitized_real"],
        result_data_spaces=["real", "desensitized_real"],
        result_limits={"max_items": 10, "max_bytes": 8192},
    )


def register_experiment_tool(registry: ToolRegistry, repository: ExperimentDatasetRepository) -> None:
    registry.register(experiment_spec(), lambda request, context: experiment_analyze(request, context, repository))
