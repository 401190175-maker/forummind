"""Run 状态机：组会-裁决-循环。"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from typing import TYPE_CHECKING

from app.agent_runtime.factory import create_runtime
from app.agent_runtime.instruction_builder import build_agent_instruction
from app.agent_runtime.result_validation import validate_agent_result
from app.agent_runtime.schemas import AgentInvocation, AgentResult, RuntimeSessionRef
from app.artifacts import build_master_markdown, master_artifact_filename
from app.domain.schemas import AgentProfile
from app.memory.experiment_projection import build_experiment_view
from app.demo_data.loader import load_demo_package
from app.orchestration.run_store import RunState, RunStep, RunStore
from app.scenario.schema import Scenario
from app.tools import build_synthetic_registry
from app.tools.context import ToolExecutionContext, build_tool_execution_context
from app.tools.policy import resolve_allowed_tools
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.search import KnowledgeSearch
from app.experiments.repository import ExperimentDatasetRepository
from app.literature.connectors import CrossrefConnector
from app.literature.integration import GovernedLiteratureSearch
from app.literature.repository import LiteratureLeadRepository
from app.literature.service import EvidenceProvenance, LiteratureService
from app.research.contracts import RealAgentInvocation, build_real_invocation
from app.tools.registry import build_real_registry
from app.storage.sqlite_store import SQLiteStore
from app.research.candidate_service import CandidateService
from app.research.validators import ResultValidationError

if TYPE_CHECKING:
    from app.meeting.service import MeetingService

MAX_CYCLES = 3
FREEZE_OFFSET = "meeting-1h"
_VALID_OPTIONS = {"approved", "approved_with_conditions", "returned", "deferred", "terminated"}


def _real_task_context(task: object) -> dict:
    task_id = str(getattr(task, "task_id", ""))
    data_space = str(getattr(task, "data_space", ""))
    document_ids = [str(item) for item in (getattr(task, "document_ids", []) or [])]
    dataset_refs = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        for item in (getattr(task, "dataset_refs", []) or [])
    ]
    return {
        "task_id": task_id,
        "title": str(getattr(task, "title", "")),
        "question": str(getattr(task, "question", "")),
        "data_space": data_space,
        "document_ids": document_ids,
        "allowed_document_ids": list(document_ids),
        "dataset_refs": dataset_refs,
        "allowed_dataset_refs": list(dataset_refs),
        "allowed_source_data_spaces": [data_space, "verifiable_public"],
    }


def _live_literature_search() -> GovernedLiteratureSearch:
    connector = CrossrefConnector()
    return GovernedLiteratureSearch(
        LiteratureService(connector),
        verifier=EvidenceProvenance(connector.fetcher),
    )


async def run_live_task(
    task: object,
    agent: object,
    *,
    store: SQLiteStore | None = None,
    runtime: object | None = None,
    run_store: object | None = None,
    state: RunState | None = None,
) -> RunState:
    """Run one persisted real task and stop at the candidate review gate.

    The function intentionally does not use a Scenario, demo package, or
    synthetic registry. The returned structured result remains in the Run's
    candidate context until the candidate service validates it.
    """
    durable_runs = run_store if run_store is not None else __import__(
        "app.orchestration.run_store", fromlist=["RunStore"]
    ).RunStore(store)
    task_context = _real_task_context(task)
    state = state or durable_runs.create(
        str(getattr(task, "group_chat_id", "")),
        "live",
        task_id=task_context["task_id"],
        agent_specs=[
            agent.model_dump(mode="json")
            if hasattr(agent, "model_dump") else dict(agent)
        ],
        runtime_name="pi",
        task_context=task_context,
    )
    try:
        invocation = build_real_invocation(task, agent, state)
    except Exception as exc:
        _fail_live(state, agent_id=str(getattr(agent, "agent_id", "system")),
                   runtime="pi", error=f"real invocation invalid: {exc}")
        return state
    try:
        durable_runs.ensure_run_started_event(state, agent_id=invocation.agent_id)
    except (TypeError, ValueError) as exc:
        _fail_live(
            state,
            agent_id=invocation.agent_id,
            runtime="pi",
            error=f"real task startup event failed: {exc}",
        )
        return state

    knowledge_search = KnowledgeSearch(KnowledgeRepository(store)) if store is not None else None
    registry = (
        build_real_registry(
            knowledge_search,
            state.tool_audit_recorder,
            ExperimentDatasetRepository(store) if store is not None else None,
            _live_literature_search(),
            LiteratureLeadRepository(store) if store is not None else None,
        )
        if knowledge_search is not None else None
    )
    runtime_name = _runtime_name(runtime) if runtime is not None else "pi"

    def context_factory(current: AgentInvocation):
        if store is None:
            raise ValueError("real task runtime requires durable document storage")
        return build_tool_execution_context(
            current,
            runtime_name="pi",
            task_id=invocation.task_id,
            allowed_document_ids=invocation.document_scope,
            allowed_dataset_refs=invocation.dataset_refs,
            memory_entries=state.memory.entries(),
            experiment_view={"steps": [step.payload for step in state.steps]},
        )

    try:
        selected_runtime = runtime or create_runtime(
            "pi", tool_registry=registry, context_factory=context_factory
        )
        if selected_runtime is None:
            raise RuntimeError("Pi runtime is unavailable")
        runtime_name = _runtime_name(selected_runtime)
        result = await selected_runtime.invoke(invocation)
    except Exception as exc:
        _fail_live(state, agent_id=invocation.agent_id, runtime=runtime_name,
                   error=f"real task runtime failed: {exc}")
        return state

    native_session = getattr(selected_runtime, "last_sessions", {}).get(invocation.agent_id)
    if native_session is not None:
        session_ref = RuntimeSessionRef(
            session_id=str(getattr(native_session, "session_id", "")),
            group_chat_id=state.group_chat_id, run_id=state.run_id,
            agent_id=invocation.agent_id, phase=invocation.phase,
            data_space=invocation.data_space, task_id=invocation.task_id,
            document_scope=list(invocation.document_scope),
            invocation_id=invocation.invocation_id,
            attempt=invocation.attempt,
            retry_of=invocation.retry_of,
            last_cursor=int(getattr(native_session, "cursor", 0)),
        )
        state.session_refs[invocation.agent_id] = session_ref
        durable_runs.save_runtime_session(
            session_ref,
            session_scope=str(getattr(native_session, "session_scope", "")),
            session_file=getattr(native_session, "session_file", None),
        )
        state.persist()
    if not _project_runtime_events_for_invocation(
        durable_runs, state, selected_runtime, invocation, runtime_name=runtime_name
    ):
        return state
    if not isinstance(result, AgentResult):
        _fail_live(state, agent_id=invocation.agent_id, runtime=runtime_name,
                   error="real task runtime returned an invalid AgentResult")
        return state
    if result.status != "ok" or result.agent_id != invocation.agent_id or result.data_space != invocation.data_space:
        error = result.error or (result.warnings[0] if result.warnings else "real task result is invalid")
        _fail_live(state, agent_id=invocation.agent_id, runtime=runtime_name, status=result.status, error=error)
        return state
    _append(
        state, invocation.phase, "invocation", invocation.agent_id,
        "Real Agent invocation completed",
        {
            "runtime": runtime_name, "agent_id": invocation.agent_id,
            "task_id": invocation.task_id, "data_space": invocation.data_space,
            "document_scope": list(invocation.document_scope),
            "status": result.status, "source": "live",
        },
    )
    try:
        candidate = CandidateService(store).from_agent_result(
            result,
            task_id=invocation.task_id,
            run_id=state.run_id,
            agent_id=invocation.agent_id,
        ) if store is not None else None
    except ResultValidationError as exc:
        _fail_live(
            state, agent_id=invocation.agent_id, runtime=runtime_name,
            error=f"real task candidate validation failed: {exc}",
        )
        return state
    state.task_context["candidate_result"] = result.model_dump(mode="json")
    if candidate is not None:
        state.task_context["candidate_id"] = candidate.candidate_id
        state.candidate_ids.append(candidate.candidate_id)
    state.status = "awaiting_review"
    state.phase = "awaiting_review"
    state.persist()
    return state


async def run_live_task_multi_agent(
    task: object,
    agents: Sequence[object],
    *,
    store: SQLiteStore | None = None,
    runtime: object | None = None,
    run_store: RunStore | None = None,
    state: RunState | None = None,
    review_agent: object | None = None,
    postdoc_agent: object | None = None,
    meeting_service: object | None = None,
    retry_agent_id: str = "",
    candidate_writer: Callable[[RunState, AgentInvocation, AgentResult], object | None] | None = None,
) -> RunState:
    """Run a frozen real task through the P2 role coordinator.

    The shared task API can call this additive bridge after it freezes the
    group members. Existing single-Agent callers continue using
    ``run_live_task`` unchanged.
    """
    from app.orchestration.coordinator import MultiAgentRunCoordinator

    durable_runs = run_store or RunStore(store)
    task_context = {
        **_real_task_context(task),
        "output_contract": "research_claim",
        "completion_mode": "candidate_review",
    }
    specs = [
        agent.model_dump(mode="json")
        if hasattr(agent, "model_dump")
        else dict(agent)
        for agent in agents
    ]
    if state is None:
        state = durable_runs.create(
            str(getattr(task, "group_chat_id", "")),
            "live",
            task_id=task_context["task_id"],
            agent_specs=specs,
            review_agent_spec=(
                review_agent.model_dump(mode="json")
                if hasattr(review_agent, "model_dump")
                else dict(review_agent) if review_agent is not None else None
            ),
            postdoc_agent_spec=(
                postdoc_agent.model_dump(mode="json")
                if hasattr(postdoc_agent, "model_dump")
                else dict(postdoc_agent) if postdoc_agent is not None else None
            ),
            runtime_name="pi",
            task_context=task_context,
        )
    else:
        expected_ids = [str(spec.get("agent_id", "")) for spec in specs]
        frozen_ids = [str(spec.get("agent_id", "")) for spec in state.agent_specs]
        frozen_task_id = str(
            state.task_id or state.task_context.get("task_id", "")
        )
        frozen_data_space = str(state.task_context.get("data_space", ""))
        frozen_documents = [
            str(item)
            for item in state.task_context.get(
                "allowed_document_ids", state.task_context.get("document_ids", [])
            )
        ]
        task_scope_changed = (
            state.group_chat_id != str(getattr(task, "group_chat_id", ""))
            or frozen_task_id != task_context["task_id"]
            or frozen_data_space != task_context["data_space"]
            or frozen_documents != task_context["allowed_document_ids"]
        )
        if (frozen_ids and frozen_ids != expected_ids) or task_scope_changed:
            mark_run_failed(
                state,
                error="real multi-Agent task invocation does not match the frozen Run Agent or task scope snapshot",
                runtime_name=state.runtime_name or "pi",
            )
            return state

    invocation_task = task
    if (
        retry_agent_id
        and state.status in {"failed", "running"}
        and str(getattr(task, "status", "")).strip() == "failed"
    ):
        copy_task = getattr(task, "model_copy", None)
        if callable(copy_task):
            invocation_task = copy_task(update={"status": "running"})

    try:
        for agent in agents:
            build_real_invocation(invocation_task, agent, state)
    except Exception as exc:
        mark_run_failed(
            state,
            error=f"real multi-Agent task invocation invalid: {exc}",
            runtime_name=state.runtime_name or "pi",
        )
        return state

    if store is None:
        mark_run_failed(
            state,
            error="real multi-Agent task runtime requires durable document storage",
            runtime_name="pi",
        )
        return state

    knowledge_search = KnowledgeSearch(KnowledgeRepository(store))
    registry = build_real_registry(
        knowledge_search,
        state.tool_audit_recorder,
        ExperimentDatasetRepository(store),
        _live_literature_search(),
        LiteratureLeadRepository(store),
    )

    def context_factory(current: AgentInvocation) -> ToolExecutionContext:
        return build_tool_execution_context(
            current,
            runtime_name="pi",
            task_id=current.task_id,
            allowed_document_ids=current.document_scope,
            allowed_dataset_refs=current.dataset_refs,
            memory_entries=state.memory.entries(),
            experiment_view={"steps": [step.payload for step in state.steps]},
        )

    def runtime_factory(**kwargs: object) -> object | None:
        if runtime is not None:
            return runtime
        return create_runtime(**kwargs)

    if candidate_writer is None:
        candidate_service = CandidateService(store)

        def candidate_writer(
            current_state: RunState,
            invocation: AgentInvocation,
            result: AgentResult,
        ) -> object | None:
            return candidate_service.from_agent_result(
                result,
                task_id=invocation.task_id,
                run_id=current_state.run_id,
                agent_id=invocation.agent_id,
            )

    coordinator = MultiAgentRunCoordinator(
        durable_runs,
        None,
        runtime_factory=runtime_factory,
        meeting_service=meeting_service,
        tool_registry=registry,
        context_factory=context_factory,
        candidate_writer=candidate_writer,
    )
    durable_runs._runs[state.run_id] = state
    await coordinator.run_cycle(state.run_id, retry_agent_id=retry_agent_id)
    return state


def _project_runtime_events_for_invocation(
    durable_runs: object,
    state: RunState,
    runtime: object,
    invocation: RealAgentInvocation,
    *,
    runtime_name: str = "pi",
) -> bool:
    """Persist native events after enriching them with server-owned scope."""
    from app.agent_runtime.event_bridge import project_runtime_event

    events_by_key = getattr(runtime, "last_events", {})
    raw_events = []
    if isinstance(events_by_key, dict):
        raw_events = events_by_key.get(invocation.invocation_id, [])
        if not raw_events:
            raw_events = events_by_key.get(invocation.agent_id, [])
    for raw in raw_events or []:
        event = dict(raw)
        event.setdefault("task_id", invocation.task_id)
        event.setdefault("document_scope", list(invocation.document_scope))
        event = durable_runs.prepare_runtime_event(state, event)
        try:
            project_runtime_event(state, event)
            durable_runs.save_runtime_event(state, event)
        except (TypeError, ValueError):
            _fail_live(
                state, agent_id=invocation.agent_id, runtime=runtime_name,
                error="native runtime event failed identity or scope validation",
            )
            return False
    return True

_RUNTIME_NAMES = {
    "LegacyLLMRuntime": "legacy_llm",
    "MockRuntime": "mock",
    "PiRuntime": "pi",
}

def _agent_prompt(
    agent_spec: dict, cycle_feedback: str | None, task_context: dict | None = None
) -> str:
    """Build the common claim contract from a frozen Agent profile snapshot."""
    ability = str(
        agent_spec.get("primary_ability")
        or agent_spec.get("capability")
        or "独立科研分析"
    )
    name = str(agent_spec.get("name") or agent_spec.get("agent_id") or "科研 Agent")
    task_context = task_context or {}
    topic_name = str(task_context.get("topic_name") or "泥浆基泡沫混凝土")
    topic_summary = str(
        task_context.get("topic_summary")
        or "泥浆掺量提高后，抗压强度下降、大孔比例增加"
    )
    initial_intent = task_context.get("initial_intent")
    base = (
        f"你是{name}，主能力是{ability}。\n"
        f"课题：{topic_name}。\n课题背景：{topic_summary}。\n"
    )
    if initial_intent:
        base += f"用户确认的正式任务意图：{initial_intent}。\n"
    if cycle_feedback:
        base += f"上一轮组会裁决理由：{cycle_feedback}。请基于此做更进一步的独立分析。\n"
    return base + (
        "请独立形成你的判断，输出四字段：判断 / 适用边界 / 可观察预测 / 可推翻条件。\n"
        "要求：观点必须实质不同；不得复述其他 Agent；至少给出一个可观察的区分预测，并说明它如何区分候选解释；"
        "不得把‘可能’‘相关’写成因果结论；不做客套。"
    )


def _instruction_for_spec(
    spec: dict, *, task_context: dict, topic_context: dict,
    phase: str = "independent_analysis",
    output_contract: str = "claim_four_fields",
):
    """Use the frozen instruction; construct a compatible one for old callers/tests."""
    frozen = spec.get("agent_instruction")
    if frozen:
        from app.agent_runtime.schemas import AgentInstruction

        return AgentInstruction.model_validate(frozen)
    profile = AgentProfile.model_validate(
        spec.get(
            "profile",
            {
                "agent_id": spec.get("agent_id", ""),
                "name": spec.get("name") or spec.get("agent_id") or "科研 Agent",
                "role": spec.get("role", "master_student"),
                "primary_ability": spec.get("primary_ability")
                or spec.get("capability"),
                "allowed_tools": list(spec.get("allowed_tools", [])),
            },
        )
    )
    return build_agent_instruction(
        profile,
        profile_version=str(spec.get("profile_version", "current")),
        topic_context=topic_context,
        task_context=dict(task_context),
        phase=phase,
        output_contract=output_contract,
    )


def _discussion_turn_prompt(seat: str | None, current_view: str, turn_context: str) -> str:
    if seat:
        return (
            f"你在此次讨论中担任{seat}席位。\n当前方案/观点：{current_view}\n讨论上下文：{turn_context}\n"
            "请针对上一发言提出实质性质疑或回应（证据来源、条件匹配、混杂因素、反例、可判别性、替代解释）；不做客套。"
        )
    return (
        f"你参与互助协作讨论。\n当前观点：{current_view}\n议题：{turn_context}\n"
        "请补充证据、方法建议或澄清把握不足之处；不做客套。"
    )


def _review_prompt(claims_text: str) -> str:
    return (
        "你作为博士（师兄）对以下硕士观点做组会前质量门审查。\n"
        f"观点：{claims_text}\n"
        "必须至少包含：一条反例或边界质疑、一条可推翻条件、一条缺失观察。\n"
        "字段不完整不得通过；客套性肯定不算有效挑刺。"
    )


def _runtime_name(runtime: object) -> str:
    """Return a stable label for existing and injected runtime adapters."""
    declared = getattr(runtime, "runtime_name", "")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    class_name = type(runtime).__name__
    return _RUNTIME_NAMES.get(class_name, class_name.removesuffix("Runtime").lower())


def _append(state: RunState, phase: str, kind: str, actor: str, content: str,
            payload: dict | None = None) -> RunStep:
    step = RunStep(
        id=f"step-{uuid.uuid4().hex[:12]}", phase=phase, kind=kind, actor=actor,
        content=content, payload=payload or {}, timestamp=time.time(),
    )
    state.steps.append(step)
    state.persist()
    return step


async def _run_live_review_gate(
    state: RunState,
    runtime: object,
    runtime_name: str,
    topic_context: dict,
    meeting_service: MeetingService | None = None,
) -> str | None:
    """Ask the frozen PhD only for a structured pre-meeting quality gate."""
    spec = state.review_agent_spec
    if not spec:
        return None
    claims = [
        {
            "agent_id": step.actor,
            "content": step.content,
            "artifact_id": step.payload.get("artifact_id"),
            "fields": {
                key: step.payload.get(key)
                for key in ("statement", "boundary", "prediction", "falsification_condition")
            },
        }
        for step in state.steps
        if step.phase == "independent_analysis" and step.kind == "claim"
    ]
    claims_text = "\n".join(
        f"{item['agent_id']}: {item['content']}" for item in claims
    )
    profile = AgentProfile.model_validate(spec.get("profile", spec))
    task_context = {
        **state.task_context,
        "claims": claims,
        "review_scope": "仅审查，不替硕士汇报，不作 PI 决策",
    }
    instruction = _instruction_for_spec(
        spec,
        task_context=task_context,
        topic_context=topic_context,
        phase="review_gate",
        output_contract="review_gate",
    )
    invocation = AgentInvocation(
        run_id=state.run_id,
        group_chat_id=state.group_chat_id,
        cycle=state.cycle,
        phase="review_gate",
        agent_id=profile.agent_id,
        role="phd_student",
        profile_version=str(spec.get("profile_version", "current")),
        agent_instruction=instruction,
        task=_review_prompt(claims_text),
        context=task_context,
        allowed_tools=list(spec.get("allowed_tools", [])),
        output_contract="review_gate",
        data_space="synthetic",
        safety_rules=[
            "只输出质量审查意见",
            "不得替硕士生成汇报",
            "不得作 PI 最终决策",
            "no_formal_memory_write",
        ],
    )
    try:
        result = await runtime.invoke(invocation)
    except Exception as exc:
        _fail_live(
            state,
            agent_id=invocation.agent_id,
            runtime=runtime_name,
            error=f"博士 review_gate 调用失败: {exc}",
            meeting_service=meeting_service,
        )
        return "failed"
    validation = validate_agent_result(invocation, result)
    if not validation.valid:
        _fail_live(
            state,
            agent_id=invocation.agent_id,
            runtime=runtime_name,
            error=result.error or validation.reason or "博士 review_gate 返回无效结果",
            status=result.status,
            meeting_service=meeting_service,
        )
        return "failed"
    raw_items = result.structured_output.get("items")
    if not isinstance(raw_items, list):
        _fail_live(
            state,
            agent_id=invocation.agent_id,
            runtime=runtime_name,
            error="博士 review_gate 必须返回 items 列表",
            meeting_service=meeting_service,
        )
        return "failed"
    required = {"counterexample", "falsification_condition", "missing_observation"}
    items: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict) or item.get("kind") not in required:
            _fail_live(
                state,
                agent_id=invocation.agent_id,
                runtime=runtime_name,
                error="博士 review_gate 的 kind 不符合审查契约",
                meeting_service=meeting_service,
            )
            return "failed"
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            _fail_live(
                state,
                agent_id=invocation.agent_id,
                runtime=runtime_name,
                error="博士 review_gate 的审查意见不能为空",
                meeting_service=meeting_service,
            )
            return "failed"
        items.append({"kind": item["kind"], "content": content.strip()})
    if {item["kind"] for item in items} != required:
        _fail_live(
            state,
            agent_id=invocation.agent_id,
            runtime=runtime_name,
            error="博士 review_gate 必须覆盖反例、可推翻条件和缺失观察",
            meeting_service=meeting_service,
        )
        return "failed"
    for item in items:
        _append(
            state,
            "review_gate",
            "review_opinion",
            invocation.agent_id,
            item["content"],
            {
                **item,
                "source": "live",
                "runtime": runtime_name,
                "agent_id": invocation.agent_id,
                "role": "phd_student",
            },
        )
    state.memory.append(
        "ReviewGate",
        {"reviewer": invocation.agent_id, "items": items, "source": "live"},
    )
    return "ok"


def run_replay(scenario: Scenario, state: RunState) -> None:
    """按 cycle 推进（replay）：独立分析 → … → 组会 awaiting_decision。"""
    cycle = scenario.cycles[state.cycle - 1]
    for master in cycle.masters:
        c = master.claim
        previous_claim = state.memory.latest("Claim", object_key=master.agent_id)
        claim_fields = {
            "statement": c.statement,
            "boundary": c.boundary,
            "prediction": c.prediction,
            "falsification_condition": c.falsification_condition,
        }
        claim_step = _append(
            state,
            "independent_analysis",
            "claim",
            master.agent_id,
            c.statement,
            {"capability": master.capability, **claim_fields},
        )
        artifact_timestamp = time.time()
        artifact_id = f"artifact:{state.run_id}:{cycle.cycle}:{master.agent_id}"
        artifact = {
            "artifact_id": artifact_id,
            "run_id": state.run_id,
            "group_chat_id": state.group_chat_id,
            "agent_id": master.agent_id,
            "artifact_type": "master_research_markdown",
            "filename": master_artifact_filename(
                timestamp=artifact_timestamp,
                task_name=str(state.task_context.get("initial_intent") or "独立分析"),
                agent_name=master.agent_id,
            ),
            "content": build_master_markdown(
                agent_name=master.agent_id,
                agent_id=master.agent_id,
                topic_name=str(state.task_context.get("topic_name") or "泥浆基泡沫混凝土"),
                initial_intent=str(state.task_context.get("initial_intent") or ""),
                content=c.statement,
                fields=claim_fields,
                runtime="scenario",
                profile_version="scenario",
                instruction_version="scenario",
                data_space="synthetic",
            ),
            "data_space": "synthetic",
            "created_at": artifact_timestamp,
            "updated_at": artifact_timestamp,
        }
        state.persist_artifact(artifact)
        claim_step.payload.update(
            {
                "source": "scenario",
                "role": "master_student",
                "agent_id": master.agent_id,
                "artifact_id": artifact_id,
                "source_refs": [artifact_id],
            }
        )
        state.persist()
        state.memory.append("Claim", {
            "agent_id": master.agent_id, "statement": c.statement,
            "status": "initial", "cycle": cycle.cycle,
        }, supersedes=previous_claim.id if previous_claim else None,
            object_key=master.agent_id)
    _run_cycle_tail(scenario, state)


def _run_cycle_tail(scenario: Scenario, state: RunState) -> None:
    cycle = scenario.cycles[state.cycle - 1]
    # discussion（可选，自由讨论·聊天室）
    for ds in cycle.discussion_sessions:
        _append(state, "discussion", "session", ds.initiator, f"自由讨论发起（{ds.trigger}）",
                {"session_id": ds.session_id, "kind": ds.kind, "trigger": ds.trigger,
                 "initiator": ds.initiator, "participants": ds.participants})
        for turn in ds.turns:
            _append(state, "discussion", "turn", turn.speaker, turn.content,
                    {"kind": turn.kind, "seat": turn.seat})
            state.memory.append("DiscussionTurn", {
                "session_id": ds.session_id, "speaker": turn.speaker,
                "kind": turn.kind, "content": turn.content, "seat": turn.seat,
            })
    # postdoc_exchange：结构化专业请求 / 范围内回答 / 范围外拒答。
    for exchange in cycle.postdoc_exchange:
        _append(state, "postdoc_exchange", exchange.kind, exchange.speaker,
                exchange.content,
                {"requester": exchange.requester, "sources": exchange.sources})
        state.memory.append("PostdocExchange", exchange.model_dump())
    # review_gate（审查意见）
    for item in cycle.review_gate.items:
        _append(state, "review_gate", "review_opinion", cycle.review_gate.reviewer,
                item.content, {"kind": item.kind})
    state.memory.append("ReviewGate", {
        "reviewer": cycle.review_gate.reviewer,
        "items": [i.model_dump() for i in cycle.review_gate.items],
    })
    # review_triggered_debate（可选，质量门触发辩论）
    for ds in cycle.review_triggered_sessions:
        _append(state, "review_triggered_debate", "session", ds.initiator,
                f"审查触发辩论（{ds.trigger}）",
                {"session_id": ds.session_id, "trigger": ds.trigger, "initiator": ds.initiator})
        for turn in ds.turns:
            _append(state, "review_triggered_debate", "turn", turn.speaker, turn.content,
                    {"kind": turn.kind, "seat": turn.seat})
            state.memory.append("DiscussionTurn", {
                "session_id": ds.session_id, "speaker": turn.speaker,
                "kind": turn.kind, "content": turn.content, "seat": turn.seat,
            })
    # revision（硕士逐条处置）
    for d in cycle.dispositions:
        _append(state, "revision", "disposition", d.actor,
                f"[{d.disposition}] {d.content}",
                {"kind": d.kind, "disposition": d.disposition, "reason": d.reason})
        state.memory.append("Disposition", d.model_dump())
    # freeze（组会前一小时锁定最终观点）
    _append(state, "freeze", "freeze", "system", "最终观点版本冻结（组会前一小时）",
            {"frozen_at": FREEZE_OFFSET, "cycle": cycle.cycle})
    if state.agent_specs:
        freeze_agent_ids = [str(spec["agent_id"]) for spec in state.agent_specs]
    else:
        freeze_agent_ids = [master.agent_id for master in cycle.masters]
    for agent_id in freeze_agent_ids:
        previous_claim = state.memory.latest("Claim", object_key=agent_id)
        if previous_claim is None:
            continue
        frozen_payload = dict(previous_claim.payload)
        frozen_payload.update(
            {"status": "frozen", "cycle": cycle.cycle, "frozen_at": FREEZE_OFFSET}
        )
        state.memory.append(
            "Claim",
            frozen_payload,
            supersedes=previous_claim.id,
            object_key=agent_id,
        )
    # meeting
    _append(state, "meeting", "agenda", "system", "；".join(cycle.meeting.agenda))
    for u in cycle.meeting.unresolved_disagreements:
        _append(state, "meeting", "unresolved", "system", u)
    sd = cycle.meeting.suggested_decision
    _append(state, "meeting", "suggested_decision", "system", f"建议裁决：{sd.option}",
            {"option": sd.option, "reason": sd.reason})
    state.status = "awaiting_decision"
    state.phase = "meeting"
    state.persist()


def _run_live_cycle_tail(scenario: Scenario, state: RunState) -> None:
    """Freeze live master artifacts and open a PI-led meeting boundary."""
    _append(
        state,
        "freeze",
        "freeze",
        "system",
        "硕士独立 Markdown 研究产物已冻结（组会前一小时）",
        {"frozen_at": FREEZE_OFFSET, "cycle": state.cycle, "source": "live"},
    )
    for spec in state.agent_specs:
        agent_id = str(spec["agent_id"])
        previous_claim = state.memory.latest("Claim", object_key=agent_id)
        if previous_claim is None:
            continue
        frozen_payload = dict(previous_claim.payload)
        frozen_payload.update(
            {"status": "frozen", "cycle": state.cycle, "frozen_at": FREEZE_OFFSET}
        )
        state.memory.append(
            "Claim",
            frozen_payload,
            supersedes=previous_claim.id,
            object_key=agent_id,
        )
    topic = state.task_context.get("topic_name", "当前研究课题")
    _append(
        state,
        "meeting",
        "agenda",
        "system",
        f"PI 主持正式组会：审阅 {topic} 的各硕士独立 Markdown 产物",
        {"source": "live", "masters_present": [spec["agent_id"] for spec in state.agent_specs]},
    )
    suggestion = dict(state.pi_suggestion)
    if not suggestion:
        suggestion = {
            "option": "pending",
            "reason": "候选材料已完成，等待 PI 依据组会材料裁决",
            "source": "live",
            "source_refs": [],
        }
        state.pi_suggestion = suggestion
    _append(
        state,
        "meeting",
        "suggested_decision",
        "system",
        str(suggestion.get("reason") or "正式组会材料已准备，等待 PI 最终决策"),
        {**suggestion, "source": "live"},
    )
    state.status = "awaiting_decision"
    state.phase = "meeting"
    state.persist()


def apply_decision(scenario: Scenario, state: RunState, option: str, reason: str) -> None:
    """PI 真交互裁决：推进 / 下一 cycle / 终止。"""
    if option not in _VALID_OPTIONS:
        raise ValueError(f"非法裁决：{option}")
    if state.status != "awaiting_decision" or state.phase != "meeting":
        raise ValueError("只能在 awaiting_decision 的 meeting 阶段进行 PI 裁决")
    _append(state, "meeting", "decision", "PI", f"{option}: {reason}",
            {"option": option, "reason": reason})
    state.memory.append("Decision", {"cycle": state.cycle, "option": option, "reason": reason})
    previous_research_state = state.memory.latest("ResearchState", object_key="research-state")
    state.memory.append(
        "ResearchState",
        {"summary": scenario.final_state.summary, "cycle": state.cycle},
        object_key="research-state",
        supersedes=previous_research_state.id if previous_research_state else None,
    )

    if option in ("approved", "approved_with_conditions"):
        de = scenario.discriminating_experiment
        claim_refs = [
            latest.id
            for master in scenario.cycles[state.cycle - 1].masters
            if (latest := state.memory.latest("Claim", object_key=master.agent_id)) is not None
        ]
        state.memory.append("ExperimentPlan", {
            **de.model_dump(),
            "claim_refs": claim_refs,
            "approval_option": option,
            "approval_reason": reason,
        })
        _append(state, "discriminating_experiment", "plan", "agent-phd-1",
                "最小判别实验方案", de.model_dump())
        state.status = "completed"
        state.phase = "discriminating_experiment"
    elif option in ("returned", "deferred"):
        state.cycle += 1
        if state.cycle > MAX_CYCLES or state.cycle > len(scenario.cycles):
            state.status = "cycle_exhausted"
            state.phase = "cycle_exhausted"
        else:
            state.steps[-1].payload["next_meeting"] = scenario.cycles[state.cycle - 1].scheduled_for
            run_replay(scenario, state)
    elif option == "terminated":
        state.status = "terminated"
        state.phase = "terminated"
    state.persist()


def run_import(scenario: Scenario, state: RunState) -> None:
    """导入结果 → 假设更新 → conclusion。"""
    if state.phase == "conclusion":
        raise ValueError("实验结果已经导入，不能重复导入")
    if state.phase != "discriminating_experiment":
        raise ValueError("只能在 discriminating_experiment 阶段导入实验结果")
    er = scenario.experiment_results
    plan = state.memory.latest("ExperimentPlan")
    result_entry = state.memory.append("ExperimentResult", {
        **er.model_dump(),
        "plan_ref": plan.id if plan else None,
    })
    _append(state, "data_import", "results", "system", "导入 demo 实验结果", er.model_dump())
    for upd in scenario.hypothesis_updates:
        claim = state.memory.latest("Claim", object_key=upd.claim_id)
        state.memory.append("HypothesisUpdate", {
            **upd.model_dump(),
            "causal_boundary": "支持程度变化不等于因果证明",
            "result_ref": result_entry.id,
            "claim_ref": claim.id if claim else None,
        })
        _append(state, "data_import", "hypothesis_update", "agent-phd-1",
                f"{upd.claim_id}: {upd.status}", upd.model_dump())
    _append(state, "conclusion", "conclusion", "agent-phd-1",
            scenario.final_state.summary, {"mechanism_draft": scenario.final_state.mechanism_draft})
    previous_research_state = state.memory.latest("ResearchState", object_key="research-state")
    state.memory.append(
        "ResearchState",
        {
            "summary": scenario.final_state.summary,
            "mechanism_draft": scenario.final_state.mechanism_draft,
            "trigger": "demo_experiment_result_import",
            "trigger_ref": result_entry.id,
        },
        object_key="research-state",
        supersedes=previous_research_state.id if previous_research_state else None,
    )
    state.phase = "conclusion"
    state.status = "conclusion"
    state.persist()


def _fail_live(
    state: RunState,
    *,
    agent_id: str,
    runtime: str,
    error: str,
    status: str = "error",
    source_refs: list[str] | None = None,
    phase: str | None = None,
    invocation_id: str | None = None,
    attempt: int | None = None,
    retry_of: str | None = None,
    meeting_service: MeetingService | None = None,
) -> None:
    """Stop a live Run without converting the failed attempt to Scenario data."""
    transaction = (
        meeting_service.transaction(state.run_id)
        if meeting_service is not None
        else nullcontext()
    )
    with transaction:
        payload = {
            "agent_id": agent_id,
            "runtime": runtime,
            "status": status,
            "error": error,
            "source_refs": list(source_refs or []),
        }
        if invocation_id is not None:
            payload["invocation_id"] = invocation_id
        if attempt is not None:
            payload["attempt"] = attempt
        if retry_of is not None:
            payload["retry_of"] = retry_of
        failure_step = _append(
            state,
            phase or "independent_analysis",
            "invocation",
            agent_id,
            error,
            payload,
        )
        state.status = "failed"
        state.phase = "failed"
        state.error = error
        state.persist()
        if meeting_service is not None:
            meeting_service.sync_live_reports(state)
            meeting_service.append_failure(
                state,
                error,
                source_refs=[failure_step.id, *(source_refs or [])],
            )


def mark_run_failed(
    state: RunState,
    *,
    error: str,
    runtime_name: str,
    agent_id: str = "system",
    source_refs: list[str] | None = None,
    meeting_service: MeetingService | None = None,
) -> None:
    """Persist a failed live Run from API preflight or runtime execution."""
    _fail_live(
        state,
        agent_id=agent_id,
        runtime=runtime_name,
        error=error,
        source_refs=source_refs,
        meeting_service=meeting_service,
    )


async def run_live(
    scenario: Scenario,
    state: RunState,
    *,
    meeting_service: MeetingService | None = None,
) -> None:
    """通过 Agent Runtime Adapter 真调 LLM 生成独立分析观点（design §6.4）。

    - `run_live()` 不再直接调用 `chat()`，而是构造 `AgentInvocation`
      并调用 `AgentRuntime.invoke()`（design §3.7）。
    - runtime 返回并通过校验的 `ok` 结果才可写入 live claim step。
    - 任一 Agent 调用失败就停止 Run，保留此前步骤，不回退为 Scenario Claim。
    - 所有 Agent 成功后复用剧本推进后续结构化阶段，replay 行为不变。
    """
    from app.orchestration.coordinator import MultiAgentRunCoordinator

    run_store = getattr(state._persist_callback, "__self__", None)
    if not isinstance(run_store, RunStore):
        run_store = RunStore()
        state._persist_callback = run_store.save
        state._artifact_callback = run_store.save_artifact
    coordinator = MultiAgentRunCoordinator(
        # This passes the module-level factory so existing test doubles that
        # monkeypatch engine.create_runtime remain compatible.
        run_store,
        scenario,
        runtime_factory=create_runtime,
        meeting_service=meeting_service,
    )
    # The API owns the long-lived RunStore; recover the passed state into the
    # coordinator's view without changing the public run_live signature.
    coordinator._run_store._runs[state.run_id] = state
    await coordinator.run_cycle(state.run_id)
