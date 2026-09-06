import pytest

from app.agent_runtime.schemas import AgentInvocation
from app.domain.schemas import AgentProfile
from app.research.contracts import build_real_invocation
from app.orchestration.run_store import RunStore
from app.tasks.schemas import ResearchTask


def _task(data_space: str = "desensitized_real") -> ResearchTask:
    return ResearchTask(
        task_id="task-real-1",
        group_chat_id="gc-real-1",
        title="孔结构研究",
        question="孔结构如何影响抗压强度？",
        document_ids=["doc-a"],
        data_space=data_space,
        status="ready",
        created_at=1.0,
        updated_at=1.0,
    )


def _agent() -> AgentProfile:
    return AgentProfile(
        agent_id="agent-real-1",
        name="真实分析 Agent",
        role="master_student",
        primary_ability="机制分析",
        allowed_data_spaces=["desensitized_real"],
        allowed_tools=["knowledge.search"],
    )


def _run(task: ResearchTask):
    return RunStore().create(
        task.group_chat_id,
        "live",
        task_id=task.task_id,
        task_context={
            "task_id": task.task_id,
            "data_space": task.data_space,
            "document_ids": task.document_ids,
        },
    )


def test_real_invocation_scopes_documents_and_uses_real_contract():
    task = _task()
    invocation = build_real_invocation(task, _agent(), _run(task))

    assert invocation.task_id == task.task_id
    assert invocation.data_space == "desensitized_real"
    assert invocation.document_scope == ["doc-a"]
    assert invocation.output_contract == "research_claim"
    assert "foam_concrete_case" not in invocation.task
    assert invocation.allowed_tools == ["knowledge.search"]


def test_real_invocation_cannot_be_created_from_synthetic_task():
    task = _task("synthetic")

    with pytest.raises(ValueError, match="real data space"):
        build_real_invocation(task, _agent(), _run(task))


def test_real_invocation_remains_an_agent_invocation_for_runtime_adapters():
    task = _task()
    invocation = build_real_invocation(task, _agent(), _run(task))

    assert isinstance(invocation, AgentInvocation)
    assert invocation.context["allowed_document_ids"] == ["doc-a"]
