"""HTTP API router for validated experiment datasets and safe analysis."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.experiments.analysis import AnalysisError, AnalysisService
from app.experiments.importers import ExperimentImportError, ExperimentImporter
from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import (
    AnalysisResult,
    AnalysisSpec,
    DatasetImportMetadata,
    ExperimentDataset,
    ExperimentDatasetSummary,
    ExperimentPreview,
)
from app.storage.repositories import GroupChatRepository
from app.storage.sqlite_store import SQLiteStore


router = APIRouter(tags=["experiments"])
_repository: ExperimentDatasetRepository | None = None
_importer: ExperimentImporter | None = None
_analysis: AnalysisService | None = None
_groups: GroupChatRepository | None = None


def configure_persistence(store: SQLiteStore | None, *, source_root: str | Path | None = None) -> None:
    global _repository, _importer, _analysis, _groups
    if store is None:
        _repository = None
        _importer = None
        _analysis = None
        _groups = None
        return
    _repository = ExperimentDatasetRepository(store)
    _importer = ExperimentImporter(_repository, source_root=source_root)
    _analysis = AnalysisService(_repository)
    _groups = GroupChatRepository(store)


def _services() -> tuple[
    ExperimentImporter, ExperimentDatasetRepository, AnalysisService, GroupChatRepository
]:
    if _importer is None or _repository is None or _analysis is None or _groups is None:
        raise HTTPException(status_code=503, detail="experiment service is unavailable")
    return _importer, _repository, _analysis, _groups


def _group_or_none(group_chat_id: str, groups: GroupChatRepository) -> dict | None:
    return groups.get(group_chat_id)


@router.post(
    "/group-chats/{group_chat_id}/experiment-datasets",
    response_model=ExperimentDataset,
    status_code=201,
)
async def import_experiment_dataset(
    group_chat_id: str,
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    source_document_id: str | None = Form(default=None),
    data_space: str | None = Form(default=None),
    source_mode: str = Form("live"),
    sample_schema: str = Form(...),
    units: str = Form("{}"),
    conditions: str = Form("{}"),
    dataset_id: str | None = Form(default=None),
) -> ExperimentDataset:
    importer, repository, _analysis, groups = _services()
    if _group_or_none(group_chat_id, groups) is None:
        raise HTTPException(status_code=404, detail="group chat not found")
    if not file.filename:
        raise HTTPException(status_code=422, detail="filename is required")
    if dataset_id:
        existing = repository.latest(dataset_id)
        if existing is not None and existing.group_chat_id != group_chat_id:
            raise HTTPException(status_code=409, detail="dataset_id belongs to another group")
    try:
        group = _group_or_none(group_chat_id, groups)
        source_id = f"experiment-source-{uuid4().hex}"
        trusted_project = f"group-project:{group_chat_id}"
        trusted_space = str(group["data_space"])
        trusted_source = source_id
        resolved_schema = _json_object(sample_schema, "sample_schema")
        resolved_units = _json_object(units, "units")
        if group is not None and not resolved_units:
            resolved_units = {
                column: "unitless"
                for column, field_type in resolved_schema.items()
                if field_type == "number"
            }
        metadata = DatasetImportMetadata(
            dataset_id=(dataset_id or f"dataset-{uuid4().hex}"),
            project_id=trusted_project,
            group_chat_id=group_chat_id,
            source_document_id=trusted_source,
            data_space=trusted_space,
            source_mode=source_mode,
            sample_schema=resolved_schema,
            units=resolved_units,
            conditions=_json_object(conditions, "conditions"),
        )
        content = await file.read()
        return importer.import_bytes(content, filename=file.filename, metadata=metadata)
    except (ExperimentImportError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=_error_detail(exc)) from exc


@router.post(
    "/group-chats/{group_chat_id}/experiment-datasets/preview",
    response_model=ExperimentPreview,
)
async def preview_experiment_dataset(
    group_chat_id: str,
    file: UploadFile = File(...),
) -> ExperimentPreview:
    importer, _repository, _analysis, _groups = _services()
    if not file.filename:
        raise HTTPException(status_code=422, detail="filename is required")
    try:
        return importer.preview(await file.read(), filename=file.filename)
    except (ExperimentImportError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=_error_detail(exc)) from exc


@router.get(
    "/group-chats/{group_chat_id}/experiment-datasets",
    response_model=list[ExperimentDatasetSummary],
)
def list_experiment_datasets(group_chat_id: str) -> list[ExperimentDatasetSummary]:
    _importer, repository, _analysis, groups = _services()
    if groups.get(group_chat_id) is None:
        return []
    return repository.list_summaries(group_chat_id)


@router.get(
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions",
    response_model=list[ExperimentDataset],
)
def list_experiment_versions(group_chat_id: str, dataset_id: str) -> list[ExperimentDataset]:
    _importer, repository, _analysis, _groups = _services()
    return repository.list_versions(dataset_id, group_chat_id=group_chat_id)


@router.get(
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analyses",
    response_model=list[AnalysisResult],
)
def list_experiment_analyses(
    group_chat_id: str,
    dataset_id: str,
    version: int = Query(..., ge=1),
) -> list[AnalysisResult]:
    _importer, repository, _analysis, _groups = _services()
    dataset = repository.get(dataset_id, version)
    if dataset is None or dataset.group_chat_id != group_chat_id:
        raise HTTPException(status_code=404, detail="dataset not found")
    return repository.list_analyses(dataset_id, version, group_chat_id=group_chat_id)


@router.get(
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/versions/{version}/source",
)
def download_experiment_source(
    group_chat_id: str,
    dataset_id: str,
    version: int,
) -> FileResponse:
    importer, repository, _analysis, _groups = _services()
    if version < 1:
        raise HTTPException(status_code=422, detail="version must be positive")
    dataset = repository.get(dataset_id, version)
    if dataset is None or dataset.group_chat_id != group_chat_id:
        raise HTTPException(status_code=404, detail="dataset not found")
    source = repository.get_source(dataset_id, version, group_chat_id=group_chat_id)
    path = Path(source["storage_path"]) if source else (
        importer.source_root / dataset.source_document_id / dataset.source_sha256
        if importer.source_root is not None else None
    )
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="source file not found")
    return FileResponse(path, media_type="application/octet-stream", filename=dataset.filename)


@router.post(
    "/group-chats/{group_chat_id}/experiment-datasets/{dataset_id}/analysis",
    response_model=AnalysisResult,
    status_code=201,
)
def analyze_experiment_dataset(
    group_chat_id: str,
    dataset_id: str,
    spec: AnalysisSpec,
    version: int | None = Query(default=None, ge=1),
) -> AnalysisResult:
    _importer, _repository, analysis, _groups = _services()
    try:
        return analysis.analyze_dataset(
            dataset_id,
            spec,
            version=version,
            group_chat_id=group_chat_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="dataset not found") from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _json_object(value: str, field_name: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return parsed


def _error_detail(exc: Exception) -> dict[str, object]:
    detail: dict[str, object] = {"message": str(exc)}
    for name in ("code", "row_number", "column_name"):
        value = getattr(exc, name, None)
        if value is not None:
            detail[name] = value
    return detail
