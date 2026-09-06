"""SQLite repository for research tasks and document scope."""

from __future__ import annotations

from app.documents.repository import DocumentRepository
from app.experiments.repository import ExperimentDatasetRepository
from app.storage.sqlite_store import SQLiteStore
from app.tasks.schemas import DatasetVersionRef, ResearchTask
import time


class ResearchTaskRepository:
    """Persist tasks and validate every associated document in one transaction."""

    def __init__(
        self,
        store: SQLiteStore,
        documents: DocumentRepository | None = None,
        datasets: ExperimentDatasetRepository | None = None,
    ) -> None:
        self.store = store
        self.documents = documents or DocumentRepository(store)
        self.datasets = datasets or ExperimentDatasetRepository(store)

    def create(self, task: ResearchTask) -> ResearchTask:
        def operation(connection) -> None:
            for document_id in task.document_ids:
                row = connection.execute(
                    """
                    SELECT document_id, data_space FROM documents
                    WHERE document_id = ? AND group_chat_id = ?
                    """,
                    (document_id, task.group_chat_id),
                ).fetchone()
                if row is None:
                    raise ValueError(f"document is not available to task: {document_id}")
                if row["data_space"] != task.data_space:
                    raise ValueError(f"document data_space mismatch: {document_id}")
            for dataset_ref in task.dataset_refs:
                dataset = self.datasets.get(dataset_ref.dataset_id, dataset_ref.version)
                if dataset is None:
                    raise ValueError(
                        f"dataset version is not available to task: "
                        f"{dataset_ref.dataset_id}:v{dataset_ref.version}"
                    )
                if dataset.group_chat_id != task.group_chat_id:
                    raise ValueError(
                        f"dataset group_chat_id mismatch: {dataset_ref.dataset_id}:v{dataset_ref.version}"
                    )
                if dataset.data_space != task.data_space:
                    raise ValueError(
                        f"dataset data_space mismatch: {dataset_ref.dataset_id}:v{dataset_ref.version}"
                    )
            connection.execute(
                """
                INSERT INTO research_tasks
                    (task_id, group_chat_id, title, question, source_clarification_id, data_space,
                     status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.group_chat_id,
                    task.title,
                    task.question,
                    task.source_clarification_id,
                    task.data_space,
                    task.status,
                    task.created_at,
                    task.updated_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO task_documents (task_id, document_id, position)
                VALUES (?, ?, ?)
                """,
                [(task.task_id, document_id, position) for position, document_id in enumerate(task.document_ids)],
            )
            connection.executemany(
                """
                INSERT INTO research_task_dataset_refs
                    (task_id, dataset_id, dataset_version, position)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (task.task_id, ref.dataset_id, ref.version, position)
                    for position, ref in enumerate(task.dataset_refs)
                ],
            )

        if self.store.in_transaction:
            operation(self.store.connection())
        else:
            with self.store.transaction() as connection:
                operation(connection)
        return task

    def get_for_group(self, task_id: str, group_chat_id: str) -> ResearchTask | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM research_tasks
                WHERE task_id = ? AND group_chat_id = ?
                """,
                (task_id, group_chat_id),
            ).fetchone()
            if row is None:
                return None
            documents = connection.execute(
                """
                SELECT document_id FROM task_documents
                WHERE task_id = ? ORDER BY position
                """,
                (task_id,),
            ).fetchall()
            datasets = connection.execute(
                """
                SELECT dataset_id, dataset_version FROM research_task_dataset_refs
                WHERE task_id = ? ORDER BY position
                """,
                (task_id,),
            ).fetchall()
        return self._from_row(
            row,
            [item["document_id"] for item in documents],
            [DatasetVersionRef(dataset_id=item["dataset_id"], version=item["dataset_version"]) for item in datasets],
        )

    def get_for_clarification(
        self, group_chat_id: str, clarification_id: str
    ) -> ResearchTask | None:
        with self.store.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM research_tasks
                WHERE group_chat_id = ? AND source_clarification_id = ?
                """,
                (group_chat_id, clarification_id),
            ).fetchone()
            if row is None:
                return None
            documents = connection.execute(
                """
                SELECT document_id FROM task_documents
                WHERE task_id = ? ORDER BY position
                """,
                (row["task_id"],),
            ).fetchall()
            datasets = connection.execute(
                """
                SELECT dataset_id, dataset_version FROM research_task_dataset_refs
                WHERE task_id = ? ORDER BY position
                """,
                (row["task_id"],),
            ).fetchall()
        return self._from_row(
            row,
            [item["document_id"] for item in documents],
            [DatasetVersionRef(dataset_id=item["dataset_id"], version=item["dataset_version"]) for item in datasets],
        )

    def list_for_group(self, group_chat_id: str) -> list[ResearchTask]:
        with self.store.locked() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_tasks
                WHERE group_chat_id = ? ORDER BY created_at, task_id
                """,
                (group_chat_id,),
            ).fetchall()
            document_rows = {
                row["task_id"]: [item["document_id"] for item in connection.execute(
                    "SELECT document_id FROM task_documents WHERE task_id = ? ORDER BY position",
                    (row["task_id"],),
                ).fetchall()]
                for row in rows
            }
            dataset_rows = {
                row["task_id"]: [
                    DatasetVersionRef(dataset_id=item["dataset_id"], version=item["dataset_version"])
                    for item in connection.execute(
                        """
                        SELECT dataset_id, dataset_version
                        FROM research_task_dataset_refs
                        WHERE task_id = ? ORDER BY position
                        """,
                        (row["task_id"],),
                    ).fetchall()
                ]
                for row in rows
            }
        return [
            self._from_row(row, document_rows[row["task_id"]], dataset_rows[row["task_id"]])
            for row in rows
        ]

    def set_status(self, task_id: str, status: str, *, updated_at: float | None = None) -> None:
        timestamp = time.time() if updated_at is None else updated_at
        with self.store.transaction() as connection:
            cursor = connection.execute(
                "UPDATE research_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, timestamp, task_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(task_id)

    @staticmethod
    def _from_row(
        row,
        document_ids: list[str],
        dataset_refs: list[DatasetVersionRef] | None = None,
    ) -> ResearchTask:
        return ResearchTask(
            task_id=row["task_id"],
            group_chat_id=row["group_chat_id"],
            title=row["title"],
            question=row["question"],
            source_clarification_id=row["source_clarification_id"],
            document_ids=document_ids,
            dataset_refs=dataset_refs or [],
            data_space=row["data_space"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
