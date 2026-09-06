from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.experiments.repository import ExperimentDatasetRepository
from app.experiments.schemas import ExperimentDataset, ExperimentRow
from app.research.contracts import build_real_invocation
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import DatasetVersionRef, ResearchTask


def _dataset(
    *,
    dataset_id: str = "dataset-a",
    version: int = 1,
    group_chat_id: str = "group-a",
    data_space: str = "desensitized_real",
) -> ExperimentDataset:
    row = ExperimentRow(
        row_number=2,
        values={"strength": 12.5},
        source_document_id="source-a",
        source_location="source-a:row:2",
        data_space=data_space,
        source_mode="live",
        verification_status="unverified",
    )
    return ExperimentDataset(
        dataset_id=dataset_id,
        version=version,
        project_id=f"group-project:{group_chat_id}",
        group_chat_id=group_chat_id,
        source_document_id="source-a",
        filename="experiment.csv",
        source_sha256="a" * 64,
        sample_schema={"strength": "number"},
        rows=[row],
        data_space=data_space,
        source_mode="live",
        verification_status="unverified",
        created_at=1.0,
        updated_at=1.0,
    )


def _task(refs: list[DatasetVersionRef]) -> SimpleNamespace:
    return SimpleNamespace(
        task_id="task-a",
        group_chat_id="group-a",
        title="Dataset-scoped task",
        question="Compare the experiment versions",
        source_clarification_id=None,
        document_ids=[],
        dataset_refs=refs,
        data_space="desensitized_real",
        status="ready",
        created_at=1.0,
        updated_at=1.0,
    )


def test_research_task_dataset_refs_require_non_empty_id_and_positive_version() -> None:
    with pytest.raises(ValidationError):
        ResearchTask.model_validate(
            {
                "task_id": "task-a",
                "group_chat_id": "group-a",
                "title": "Task",
                "question": "Question",
                "dataset_refs": [{"dataset_id": " ", "version": 1}],
                "data_space": "desensitized_real",
                "status": "ready",
                "created_at": 1.0,
                "updated_at": 1.0,
            }
        )
    with pytest.raises(ValidationError):
        ResearchTask.model_validate(
            {
                "task_id": "task-a",
                "group_chat_id": "group-a",
                "title": "Task",
                "question": "Question",
                "dataset_refs": [{"dataset_id": "dataset-a", "version": 0}],
                "data_space": "desensitized_real",
                "status": "ready",
                "created_at": 1.0,
                "updated_at": 1.0,
            }
        )


def test_research_task_rejects_duplicate_dataset_versions() -> None:
    with pytest.raises(ValidationError):
        ResearchTask(
            task_id="task-a",
            group_chat_id="group-a",
            title="Task",
            question="Question",
            dataset_refs=[
                {"dataset_id": "dataset-a", "version": 1},
                {"dataset_id": "dataset-a", "version": 1},
            ],
            data_space="desensitized_real",
            status="ready",
            created_at=1.0,
            updated_at=1.0,
        )


def test_research_task_repository_persists_ordered_dataset_refs_and_reopens(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "dataset-scope.db")
    store.initialize()
    datasets = ExperimentDatasetRepository(store)
    datasets.save(_dataset(dataset_id="dataset-a", version=1))
    datasets.save(_dataset(dataset_id="dataset-b", version=2))
    repository = ResearchTaskRepository(store)
    task = _task(
        [
            DatasetVersionRef(dataset_id="dataset-b", version=2),
            DatasetVersionRef(dataset_id="dataset-a", version=1),
        ]
    )

    repository.create(task)
    store.close()

    reopened = SQLiteStore(tmp_path / "dataset-scope.db")
    reopened.initialize()
    restored = ResearchTaskRepository(reopened).get_for_group("task-a", "group-a")
    assert restored is not None
    assert restored.dataset_refs == task.dataset_refs
    reopened.close()


@pytest.mark.parametrize(
    ("dataset", "message"),
    [
        (_dataset(group_chat_id="group-b"), "group_chat_id"),
        (_dataset(data_space="real"), "data_space"),
    ],
)
def test_research_task_repository_rejects_dataset_outside_task_scope(
    tmp_path, dataset: ExperimentDataset, message: str
) -> None:
    store = SQLiteStore(tmp_path / "dataset-scope.db")
    store.initialize()
    ExperimentDatasetRepository(store).save(dataset)

    with pytest.raises(ValueError, match=message):
        ResearchTaskRepository(store).create(
            _task([DatasetVersionRef(dataset_id=dataset.dataset_id, version=dataset.version)])
        )
    store.close()


def test_real_invocation_carries_server_owned_dataset_refs() -> None:
    task = _task([DatasetVersionRef(dataset_id="dataset-a", version=3)])
    agent = SimpleNamespace(
        agent_id="agent-a",
        name="Agent A",
        role="master_student",
        allowed_data_spaces=["desensitized_real"],
        allowed_tools=["knowledge.search"],
        primary_ability="analysis",
    )
    run = SimpleNamespace(
        run_id="run-a",
        group_chat_id="group-a",
        mode="live",
        cycle=1,
        profile_version="current",
        task_context={},
    )

    invocation = build_real_invocation(task, agent, run)

    assert invocation.context["allowed_dataset_refs"] == [
        {"dataset_id": "dataset-a", "version": 3}
    ]
