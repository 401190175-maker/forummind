"""End-to-end proof for the P3 governed source and approval boundary."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import candidates as candidates_api
from app.api import experiments as experiments_api
from app.api import research_tasks as research_tasks_api
from app.api import runs as runs_api
from app.agent_runtime.schemas import AgentInvocation, AgentResult
from app.experiments.repository import ExperimentDatasetRepository
from app.literature.integration import GovernedLiteratureSearch
from app.literature.repository import LiteratureLeadRepository
from app.literature.schemas import LiteratureLead
from app.literature.service import LiteratureService
from app.orchestration.run_store import RunStore
from app.research.candidate_service import CandidateService
from app.research.evidence_repository import EvidenceRepository
from app.research.state_repository import ResearchStateRepository
from app.research.contracts import CandidateClaim
from app.storage.sqlite_store import SQLiteStore
from app.tasks.repository import ResearchTaskRepository
from app.tasks.schemas import DatasetVersionRef, ResearchTask
from app.tools.context import build_tool_execution_context
from app.tools.experiment import register_experiment_tool
from app.tools.literature import register_literature_tool
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest


_DATASET_BYTES = b"sample_id,strength\nS-1,3.2\n"


class _LiteratureConnector:
    def __init__(self, lead: LiteratureLead) -> None:
        self.lead = lead

    def search(self, query, filters):
        return [self.lead]


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "p3.db"
    store = SQLiteStore(path)
    store.initialize()
    with store.transaction() as connection:
        connection.execute(
            "INSERT INTO group_chats (group_chat_id, data_space, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("group-p3", "desensitized_real", "{}", 1.0, 1.0),
        )
    monkeypatch.setattr(runs_api, "run_store", RunStore(store))
    for name in ("_meeting_repository", "_meeting_service", "_store", "_task_repository"):
        monkeypatch.setattr(runs_api, name, getattr(runs_api, name))
    monkeypatch.setattr(candidates_api, "_service", candidates_api._service)
    for name in ("_repository", "_importer", "_analysis", "_groups"):
        monkeypatch.setattr(experiments_api, name, getattr(experiments_api, name))
    for name in ("_tasks", "_groups"):
        monkeypatch.setattr(research_tasks_api, name, getattr(research_tasks_api, name))
    runs_api.configure_persistence(store)
    candidates_api.configure_persistence(store)
    experiments_api.configure_persistence(store, source_root=tmp_path / "sources")
    research_tasks_api.configure_persistence(store)
    application = FastAPI()
    application.include_router(runs_api.router)
    application.include_router(candidates_api.router)
    application.include_router(experiments_api.router)
    application.include_router(research_tasks_api.router)
    client = TestClient(application)
    imported = client.post(
        "/group-chats/group-p3/experiment-datasets",
        data={
            "sample_schema": '{"sample_id":"sample_id","strength":"number"}',
            "dataset_id": "foam-data",
        },
        files={"file": ("results.csv", _DATASET_BYTES, "text/csv")},
    )
    assert imported.status_code == 201
    assert imported.json()["version"] == 1
    ResearchTaskRepository(store).create(ResearchTask(
        task_id="task-experiment", group_chat_id="group-p3", title="实验任务", question="强度？",
        dataset_refs=[DatasetVersionRef(dataset_id="foam-data", version=1)],
        data_space="desensitized_real", status="ready", created_at=1.0, updated_at=1.0,
    ))
    return path, store, client


def _context(state, *, agent_id: str, allowed_tools: list[str], refs=None):
    invocation = AgentInvocation(
        run_id=state.run_id, group_chat_id="group-p3", cycle=1,
        phase="independent_analysis", agent_id=agent_id, role="master_student",
        task="source", allowed_tools=allowed_tools, data_space="desensitized_real",
        task_id=state.task_id, dataset_refs=refs or [],
        context={"task_id": state.task_id, "allowed_dataset_refs": [item.model_dump(mode="json") for item in (refs or [])]},
    )
    return build_tool_execution_context(
        invocation, runtime_name="pi", allowed_dataset_refs=refs or [],
        allowed_source_data_spaces=["desensitized_real", "verifiable_public"],
    )


def test_experiment_and_literature_sources_reach_approval_and_survive_restart(tmp_path, monkeypatch):
    path, store, client = _setup(tmp_path, monkeypatch)
    runs = runs_api.run_store
    state = runs.create(
        "group-p3", "live", task_id="task-experiment",
        agent_specs=[{"agent_id": "agent-a", "role": "master_student"}],
        task_context={"data_space": "desensitized_real", "allowed_dataset_refs": [{"dataset_id": "foam-data", "version": 1}]},
    )
    registry = ToolRegistry(state.tool_audit_recorder)
    register_experiment_tool(registry, ExperimentDatasetRepository(store))
    context = _context(state, agent_id="agent-a", allowed_tools=["experiment.analyze"], refs=[DatasetVersionRef(dataset_id="foam-data", version=1)])
    result = registry.execute(ToolRequest(
        request_id="analysis-1", name="experiment.analyze", data_space="desensitized_real",
        arguments={"dataset_id": "foam-data", "dataset_version": 1, "operation": "summary", "column_name": "strength"},
    ), context)
    assert result.status == "ok"
    assert result.source_refs[0].startswith("analysis:")
    denied = registry.execute(ToolRequest(
        request_id="analysis-2", name="experiment.analyze", data_space="desensitized_real",
        arguments={"dataset_id": "foam-data", "dataset_version": 2, "operation": "summary", "column_name": "strength"},
    ), context)
    assert denied.status == "error"
    assert denied.error_code == "dataset_scope_denied"

    candidate = CandidateService(store).create(CandidateClaim(
        candidate_id="candidate-analysis", task_id="task-experiment", run_id=state.run_id,
        agent_id="agent-a", claim="强度均值为 3.2。", evidence_refs=result.source_refs,
        reasoning_summary="分析结果", uncertainty="单个样本", next_action="补样", data_space="desensitized_real",
    ))
    state.status = "awaiting_review"
    state.persist()
    listed = client.get(f"/runs/{state.run_id}/candidates")
    assert listed.status_code == 200
    experiment_evidence = listed.json()[0]["evidence"][0]
    assert experiment_evidence["source_ref"] == result.source_refs[0]
    assert experiment_evidence["source_type"] == "experiment"
    assert experiment_evidence["analysis_id"] == result.source_refs[0].removeprefix("analysis:")
    assert experiment_evidence["dataset_id"] == "foam-data"
    assert experiment_evidence["dataset_version"] == 1
    assert experiment_evidence["source_filename"] == "results.csv"
    assert experiment_evidence["document_id"] is None

    source = client.get(
        "/group-chats/group-p3/experiment-datasets/foam-data/versions/1/source"
    )
    assert source.status_code == 200
    assert source.content == _DATASET_BYTES

    approved = client.post(
        f"/runs/{state.run_id}/candidates/{candidate.candidate_id}/approve",
        json={"actor_id": "user"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    persisted_run = client.get(f"/runs/{state.run_id}")
    assert persisted_run.json()["status"] == "completed"
    assert persisted_run.json()["phase"] == "conclusion"
    persisted_tasks = client.get("/group-chats/group-p3/tasks").json()
    assert next(item for item in persisted_tasks if item["task_id"] == "task-experiment")["status"] == "completed"
    assert ResearchStateRepository(store).get_head("group-p3")["version"] == 1

    lead = LiteratureLead(
        lead_id="lit-1", title="Foam concrete strength", doi="10.1000/foam",
        url="https://doi.org/10.1000/foam", source_location="doi:10.1000/foam",
        data_space="verifiable_public", source_mode="live", verification_status="verified",
    )
    ResearchTaskRepository(store).create(ResearchTask(
        task_id="task-literature", group_chat_id="group-p3", title="文献任务", question="证据？",
        data_space="desensitized_real", status="ready", created_at=2.0, updated_at=2.0,
    ))
    state_lit = runs.create(
        "group-p3", "live", task_id="task-literature",
        agent_specs=[{"agent_id": "agent-b", "role": "master_student"}],
        task_context={"data_space": "desensitized_real"},
    )
    literature_registry = ToolRegistry(state_lit.tool_audit_recorder)
    search = GovernedLiteratureSearch(LiteratureService(_LiteratureConnector(lead)))
    register_literature_tool(literature_registry, search, LiteratureLeadRepository(store))
    lit_result = literature_registry.execute(ToolRequest(
        request_id="literature-1", name="literature.search", data_space="desensitized_real",
        arguments={"query": "foam", "verify": False},
    ), _context(state_lit, agent_id="agent-b", allowed_tools=["literature.search"]))
    assert lit_result.status == "ok"
    lit_candidate = CandidateService(store).create(CandidateClaim(
        candidate_id="candidate-literature", task_id="task-literature", run_id=state_lit.run_id,
        agent_id="agent-b", claim="公开文献提供了相关背景。", evidence_refs=lit_result.source_refs,
        reasoning_summary="文献线索", uncertainty="需核对全文", next_action="人工核查", data_space="desensitized_real",
    ))
    literature_evidence = CandidateService(store).get(lit_candidate.candidate_id).evidence[0]
    assert literature_evidence.source_ref == "literature:lit-1"
    assert literature_evidence.source_type == "literature"
    assert literature_evidence.source_url == "https://doi.org/10.1000/foam"
    assert literature_evidence.document_id is None
    CandidateService(store).approve(lit_candidate.candidate_id, "user")
    store.close()

    reopened = SQLiteStore(path)
    reopened.initialize()
    runs_api.run_store = RunStore(reopened)
    runs_api.configure_persistence(reopened)
    candidates_api.configure_persistence(reopened)
    experiments_api.configure_persistence(reopened, source_root=tmp_path / "sources")
    research_tasks_api.configure_persistence(reopened)
    restored_candidate = client.get(f"/runs/{state.run_id}/candidates")
    assert restored_candidate.status_code == 200
    assert restored_candidate.json()[0]["status"] == "approved"
    assert restored_candidate.json()[0]["evidence"][0]["dataset_version"] == 1
    restored_run = client.get(f"/runs/{state.run_id}")
    assert restored_run.json()["status"] == "completed"
    assert restored_run.json()["phase"] == "conclusion"
    restored_tasks = client.get("/group-chats/group-p3/tasks").json()
    assert next(item for item in restored_tasks if item["task_id"] == "task-experiment")["status"] == "completed"
    restored_source = client.get(
        "/group-chats/group-p3/experiment-datasets/foam-data/versions/1/source"
    )
    assert restored_source.status_code == 200
    assert restored_source.content == _DATASET_BYTES
    assert LiteratureLeadRepository(reopened).get("literature:lit-1") is not None
    assert EvidenceRepository(reopened).list_for_candidate("candidate-analysis")
    assert ResearchStateRepository(reopened).get_head("group-p3")["version"] == 2
    assert len(ResearchStateRepository(reopened).list_versions("group-p3")) == 2
    reopened.close()
