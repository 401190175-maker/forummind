"""ForumMind-owned multi-Agent research-cycle orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

from app.agent_runtime.instruction_builder import (
    RoleInvocationBuilder,
    build_agent_instruction,
)
from app.agent_runtime.result_validation import normalize_review_items, validate_agent_result
from app.agent_runtime.schemas import (
    AgentInstruction,
    AgentInvocation,
    AgentResult,
    PostdocSynthesis,
    ReviewGateResult,
    RuntimeSessionRef,
)
from app.artifacts import build_master_markdown, master_artifact_filename
from app.domain.schemas import AgentProfile
from app.demo_data.loader import load_demo_package
from app.memory.experiment_projection import build_experiment_view
from app.orchestration.run_store import RunState, RunStore
from app.scenario.schema import Scenario
from app.tools import build_synthetic_registry
from app.tools.context import ToolExecutionContext, build_tool_execution_context
from app.tools.policy import resolve_allowed_tools

MAX_AGENT_ATTEMPTS = 2


@dataclass(frozen=True)
class InvocationRecord:
    invocation: AgentInvocation
    status: str
    session_id: str = ""


@dataclass
class MultiAgentRunResult:
    """Result envelope for one coordinator cycle."""

    state: RunState
    invocations: list[InvocationRecord] = field(default_factory=list)
    reviewer: ReviewGateResult | None = None
    postdoc: PostdocSynthesis | None = None


RuntimeFactory = Callable[..., object | None]
ContextFactory = Callable[[AgentInvocation], ToolExecutionContext]
CandidateWriter = Callable[[RunState, AgentInvocation, AgentResult], object | None]


class MultiAgentRunCoordinator:
    """Execute role-specific Agent Sessions while ForumMind owns state changes."""

    def __init__(
        self,
        run_store: RunStore,
        scenario: Scenario | None,
        *,
        runtime_factory: RuntimeFactory,
        meeting_service: object | None = None,
        tool_registry: object | None = None,
        context_factory: ContextFactory | None = None,
        candidate_writer: CandidateWriter | None = None,
    ) -> None:
        self._run_store = run_store
        self._scenario = scenario
        self._runtime_factory = runtime_factory
        self._meeting_service = meeting_service
        if (tool_registry is None) != (context_factory is None):
            raise ValueError("tool_registry and context_factory must be provided together")
        self._tool_registry = tool_registry
        self._context_factory = context_factory
        self._candidate_writer = candidate_writer

    async def run_cycle(
        self,
        run_id: str,
        *,
        retry_agent_id: str = "",
    ) -> MultiAgentRunResult:
        from app.orchestration import engine

        state = self._run_store.get(run_id)
        if state is None:
            raise ValueError(f"Run 不存在: {run_id}")
        if state.mode != "live":
            raise ValueError("MultiAgentRunCoordinator 只处理 live Run")

        result = MultiAgentRunResult(state=state)
        masters = self._master_specs(state)
        if len(masters) < 3 or len({str(spec.get("agent_id")) for spec in masters}) != len(masters):
            self._fail(state, "system", "independent_analysis", "live Run 至少需要三个不同的冻结 master_student Agent")
            return result

        retry_phase = self._retry_phase(state, retry_agent_id)
        if state.status == "failed" and not retry_agent_id:
            return result
        if retry_agent_id:
            state.status = "running"
            state.phase = retry_phase or "independent_analysis"
            state.error = ""
            state.persist()

        if self._context_factory is not None:
            tool_registry = self._tool_registry
            context_factory = self._context_factory
        else:
            if self._scenario is None:
                self._fail(state, "system", "independent_analysis", "live Run 缺少 synthetic scenario")
                return result
            package = load_demo_package(self._scenario.package_id)
            tool_registry = build_synthetic_registry(state.tool_audit_recorder)

            def context_factory(invocation: AgentInvocation) -> ToolExecutionContext:
                view = build_experiment_view(
                    phase=state.phase,
                    steps=state.steps,
                    entries=state.memory.entries(),
                )
                view["constraints"] = self._scenario.discriminating_experiment.model_dump(mode="python")
                return build_tool_execution_context(
                    invocation,
                    runtime_name="pi",
                    memory_entries=state.memory.entries(),
                    literature_leads=package.literature_leads,
                    experiment_view=view,
                )

        try:
            runtime = self._make_runtime(state.runtime_name or None, tool_registry, context_factory)
        except Exception as exc:
            self._fail(state, "system", "independent_analysis", f"Agent runtime 初始化失败: {exc}")
            return result
        if runtime is None:
            self._fail(state, "system", "independent_analysis", "Agent runtime 不可用")
            return result

        runtime_name = self._runtime_name(runtime)
        topic_context = {
            "name": state.task_context.get("topic_name", "泥浆基泡沫混凝土"),
            "summary": state.task_context.get("topic_summary", "合成科研课题"),
        }
        completed = self._completed_masters(state)
        start_index = 0
        if retry_agent_id and retry_phase == "independent_analysis":
            start_index = next(
                (index for index, spec in enumerate(masters) if str(spec.get("agent_id")) == retry_agent_id),
                len(masters),
            )
        for index, spec in enumerate(masters):
            agent_id = str(spec.get("agent_id", ""))
            if retry_agent_id and retry_phase != "independent_analysis":
                continue
            if index < start_index or (not retry_agent_id and agent_id in completed):
                continue
            invocation = self._build_invocation(
                state,
                spec,
                phase="independent_analysis",
                topic_context=topic_context,
                task=(
                    f"{state.task_context.get('task', state.task_context.get('initial_intent', '比较候选机制'))}"
                ),
                input_refs=[],
            )
            invoked = await self._invoke(
                state,
                runtime,
                runtime_name,
                invocation,
                context_factory,
                result,
            )
            if invoked is None:
                return result
            try:
                recorded = self._record_master(
                    state, spec, invocation, invoked, runtime_name=runtime_name
                )
            except Exception as exc:
                self._fail(
                    state,
                    invocation.agent_id,
                    invocation.phase,
                    f"Agent 候选写入失败: {exc}",
                    runtime_name=runtime_name,
                    invocation=invocation,
                )
                return result
            if not recorded:
                return result
            completed.add(agent_id)

        if len(completed) < 3:
            return result

        should_review = bool(state.review_agent_spec)
        review_retry = retry_phase == "review_gate"
        if should_review and (not state.review_result or review_retry):
            review = await self._run_review(
                state,
                runtime,
                runtime_name,
                topic_context,
                context_factory,
                result,
            )
            if review is None or review.disposition != "approved":
                return result

        should_postdoc = bool(state.postdoc_agent_spec)
        postdoc_retry = retry_phase == "postdoc_exchange"
        if should_postdoc and (not state.postdoc_result or postdoc_retry):
            postdoc = await self._run_postdoc(
                state,
                runtime,
                runtime_name,
                topic_context,
                context_factory,
                result,
            )
            if postdoc is None:
                return result

        if state.status != "awaiting_decision":
            if state.task_context.get("completion_mode") == "candidate_review":
                if state.pi_suggestion and not any(
                    step.kind == "suggested_decision" for step in state.steps
                ):
                    engine._append(
                        state,
                        "postdoc_exchange",
                        "suggested_decision",
                        "system",
                        str(state.pi_suggestion.get("reason") or "候选材料已准备，等待 PI 审阅"),
                        {**state.pi_suggestion, "source": "live"},
                    )
                state.status = "awaiting_review"
                state.phase = "awaiting_review"
                state.persist()
                sync_task_materials = getattr(self._meeting_service, "sync_task_materials", None)
                if callable(sync_task_materials):
                    sync_task_materials(state)
                return result
            if not state.pi_suggestion:
                state.pi_suggestion = {
                    "option": "pending",
                    "reason": "候选材料已完成，等待 PI 依据组会材料裁决",
                    "source": "live",
                    "source_refs": [],
                }
            engine._run_live_cycle_tail(self._scenario, state)
            if self._meeting_service is not None:
                self._meeting_service.sync_live_reports(state)
        return result

    async def retry_agent(self, run_id: str, agent_id: str) -> MultiAgentRunResult:
        state = self._run_store.get(run_id)
        if state is None:
            raise ValueError(f"Run 不存在: {run_id}")
        if state.status != "failed":
            raise ValueError("只能重试 failed Run")
        failures = [
            step
            for step in reversed(state.steps)
            if step.kind == "invocation" and step.actor == agent_id and step.payload.get("status") != "ok"
        ]
        if not failures:
            raise ValueError(f"没有找到 Agent 的失败 invocation: {agent_id}")
        attempts = int(state.agent_attempts.get(agent_id, 0))
        if attempts >= MAX_AGENT_ATTEMPTS:
            raise ValueError(f"Agent 已达到最大重试次数: {agent_id}")
        return await self.run_cycle(run_id, retry_agent_id=agent_id)

    @staticmethod
    def _master_specs(state: RunState) -> list[dict]:
        return [
            dict(spec)
            for spec in state.agent_specs
            if str(spec.get("role", "")) == "master_student"
        ]

    @staticmethod
    def _completed_masters(state: RunState) -> set[str]:
        return {
            str(step.actor)
            for step in state.steps
            if step.kind in {"claim", "candidate"}
            and step.phase == "independent_analysis"
            and step.payload.get("source") == "live"
        }

    @staticmethod
    def _retry_phase(state: RunState, agent_id: str) -> str:
        for step in reversed(state.steps):
            if step.kind == "invocation" and step.actor == agent_id and step.payload.get("status") != "ok":
                return step.phase
        return ""

    def _make_runtime(
        self,
        runtime_name: str | None,
        tool_registry: object,
        context_factory: Callable,
    ) -> object | None:
        try:
            return self._runtime_factory(
                runtime_name=runtime_name,
                tool_registry=tool_registry,
                context_factory=context_factory,
            )
        except TypeError as exc:
            if "unexpected keyword" not in str(exc):
                raise
            return self._runtime_factory()

    @staticmethod
    def _runtime_name(runtime: object) -> str:
        declared = getattr(runtime, "runtime_name", "")
        if isinstance(declared, str) and declared.strip():
            return declared.strip()
        names = {
            "LegacyLLMRuntime": "legacy_llm",
            "MockRuntime": "mock",
            "PiRuntime": "pi",
        }
        return names.get(type(runtime).__name__, type(runtime).__name__.lower())

    def _build_invocation(
        self,
        state: RunState,
        spec: dict,
        *,
        phase: str,
        topic_context: dict,
        task: str,
        input_refs: list[str],
    ) -> AgentInvocation:
        role = str(spec.get("role", "")).strip()
        data_space = str(state.task_context.get("data_space", "synthetic"))
        task_scope = {
            **spec,
            "role": role,
            "phase": phase,
            "data_space": data_space,
            "task": task,
        }
        plan = RoleInvocationBuilder.build(role, phase, task_scope)
        profile_payload = dict(spec.get("profile", spec))
        profile_payload.setdefault("agent_id", spec.get("agent_id", ""))
        profile_payload.setdefault("name", spec.get("name") or spec.get("agent_id") or "科研 Agent")
        profile_payload.setdefault("role", role)
        profile_payload.setdefault("primary_ability", spec.get("primary_ability") or "独立科研分析")
        profile = AgentProfile.model_validate(profile_payload)
        # Candidate results are persisted for the task API, while claims are
        # already passed through the role-specific context below. Sending both
        # copies makes later real invocations grow quadratically and can cross
        # the native runtime request limit.
        task_context = {
            key: value
            for key, value in state.task_context.items()
            if key != "candidate_results"
        }
        task_context.update({
            "role_scope": {
                "role": role,
                "phase": phase,
                "allowed_tools": list(plan.allowed_tools),
            },
        })
        candidate_output = (
            role == "master_student"
            and phase == "independent_analysis"
            and (
                state.task_context.get("output_contract") == "research_claim"
                or state.task_context.get("completion_mode") == "candidate_review"
            )
        )
        instruction = build_agent_instruction(
            profile,
            profile_version=str(spec.get("profile_version", "current")),
            topic_context=topic_context,
            task_context=task_context,
            phase=phase,
            allowed_tools=list(plan.allowed_tools),
            output_contract=(
                "research_claim"
                if candidate_output
                else plan.output_contract
            ),
        )
        allowed_tools = list(plan.allowed_tools)
        if state.runtime_name != "pi" and not spec.get("allowed_tools"):
            # Legacy/mock adapters never discover server tools. Preserve their
            # old empty request while Pi receives the server policy defaults.
            allowed_tools = []
        instruction.allowed_tools = list(allowed_tools)
        instruction.task_context["role_scope"]["allowed_tools"] = list(allowed_tools)
        attempt = int(state.agent_attempts.get(str(spec.get("agent_id")), 0)) + 1
        previous = self._previous_invocation(state, str(spec.get("agent_id")), phase)
        output_contract = instruction.output_contract
        invocation_task = plan.task
        if output_contract == "research_claim":
            invocation_task = (
                f"{plan.task}\n"
                "最终只输出合法 JSON 对象，字段必须为 claim、evidence_refs、"
                "reasoning_summary、uncertainty、next_action。"
                "evidence_refs 必须是授权工具结果中的裸 chunk_id 字符串数组。"
            )
        invocation = AgentInvocation(
            run_id=state.run_id,
            group_chat_id=state.group_chat_id,
            cycle=state.cycle,
            phase=phase,
            agent_id=str(spec.get("agent_id", "")),
            role=role,
            profile_version=str(spec.get("profile_version", "current")),
            agent_instruction=instruction,
            task=invocation_task,
            input_refs=list(input_refs),
            context={
                "agent_profile": dict(spec),
                "task_context": task_context,
                "topic_context": dict(topic_context),
                "cycle": state.cycle,
                "specialty_domain": spec.get("specialty_domain"),
                "review_result": dict(state.review_result),
                "claims": self._claim_context(state),
            },
            allowed_tools=allowed_tools,
            output_contract=plan.output_contract,
            data_space=data_space,
            task_id=str(state.task_id or state.task_context.get("task_id", "")),
            document_scope=[
                str(item)
                for item in state.task_context.get(
                    "allowed_document_ids", state.task_context.get("document_ids", [])
                )
            ],
            attempt=attempt,
            retry_of=previous,
            safety_rules=[
                "no_formal_memory_write",
                "no_research_state_write",
                "no_stage_transition",
                "candidate_only",
            ],
        )
        state.agent_attempts[invocation.agent_id] = attempt
        state.current_agent_id = invocation.agent_id
        state.current_phase = phase
        state.current_invocation_id = invocation.invocation_id
        state.persist()
        invocation.output_contract = output_contract
        return invocation

    @staticmethod
    def _previous_invocation(state: RunState, agent_id: str, phase: str) -> str:
        for step in reversed(state.steps):
            if (
                step.kind == "invocation"
                and step.actor == agent_id
                and step.phase == phase
                and step.payload.get("status") != "ok"
            ):
                return str(step.payload.get("invocation_id", ""))
        return ""

    @staticmethod
    def _claim_context(state: RunState) -> list[dict]:
        return [
            {
                "agent_id": step.actor,
                "content": step.content,
                "source_refs": list(step.payload.get("source_refs", [])),
            }
            for step in state.steps
            if step.kind in {"claim", "candidate"}
            and step.payload.get("source") == "live"
        ]

    async def _invoke(
        self,
        state: RunState,
        runtime: object,
        runtime_name: str,
        invocation: AgentInvocation,
        context_factory: Callable,
        outcome: MultiAgentRunResult,
    ) -> AgentResult | None:
        if runtime_name == "pi" and invocation.allowed_tools:
            decision = resolve_allowed_tools(context_factory(invocation))
            invocation.allowed_tools = [
                tool for tool in invocation.allowed_tools if tool in decision.allowed_tools
            ]
        session_ref = None
        try:
            result = await runtime.invoke(invocation)
        except Exception as exc:
            session_ref = self._save_session(state, invocation, runtime)
            self._fail(
                state,
                invocation.agent_id,
                invocation.phase,
                f"Agent 调用失败: {exc}",
                runtime_name=runtime_name,
                invocation=invocation,
            )
            outcome.invocations.append(InvocationRecord(invocation, "error", session_ref.session_id if session_ref else ""))
            return None
        session_ref = self._save_session(state, invocation, runtime)
        if not isinstance(result, AgentResult):
            self._fail(
                state,
                invocation.agent_id,
                invocation.phase,
                "Agent runtime returned an invalid AgentResult",
                runtime_name=runtime_name,
                invocation=invocation,
            )
            outcome.invocations.append(InvocationRecord(invocation, "error", session_ref.session_id if session_ref else ""))
            return None
        from app.orchestration import engine

        if not engine._project_runtime_events_for_invocation(
            self._run_store,
            state,
            runtime,
            invocation,
            runtime_name=runtime_name,
        ):
            outcome.invocations.append(InvocationRecord(invocation, "error", session_ref.session_id if session_ref else ""))
            return None
        validation = validate_agent_result(invocation, result)
        if not validation.valid:
            error = result.error or (result.warnings[0] if result.warnings else validation.reason)
            self._fail(
                state,
                invocation.agent_id,
                invocation.phase,
                error,
                status="error",
                runtime_name=runtime_name,
                invocation=invocation,
            )
            outcome.invocations.append(InvocationRecord(invocation, result.status, session_ref.session_id if session_ref else ""))
            return None
        outcome.invocations.append(InvocationRecord(invocation, "ok", session_ref.session_id if session_ref else ""))
        return result

    def _save_session(self, state: RunState, invocation: AgentInvocation, runtime: object) -> RuntimeSessionRef | None:
        sessions = getattr(runtime, "last_sessions", {})
        session = (
            sessions.get(invocation.invocation_id) or sessions.get(invocation.agent_id)
            if isinstance(sessions, dict)
            else None
        )
        if session is None:
            return None
        ref = RuntimeSessionRef(
            session_id=str(getattr(session, "session_id", "")),
            group_chat_id=state.group_chat_id,
            run_id=state.run_id,
            agent_id=invocation.agent_id,
            phase=invocation.phase,
            data_space=invocation.data_space,
            task_id=invocation.task_id,
            document_scope=list(invocation.document_scope),
            invocation_id=invocation.invocation_id,
            attempt=invocation.attempt,
            retry_of=invocation.retry_of,
            last_cursor=int(getattr(session, "cursor", 0)),
        )
        key = invocation.agent_id if invocation.attempt == 1 else f"{invocation.agent_id}:attempt-{invocation.attempt}"
        state.session_refs[key] = ref
        self._run_store.save_runtime_session(
            ref,
            session_scope=str(getattr(session, "session_scope", "")),
            session_file=getattr(session, "session_file", None),
        )
        state.persist()
        return ref

    def _record_master(
        self,
        state: RunState,
        spec: dict,
        invocation: AgentInvocation,
        result: AgentResult,
        *,
        runtime_name: str,
    ) -> bool:
        from app.orchestration import engine

        source_refs = list(invocation.input_refs)
        if result.runtime_state_ref:
            source_refs.append(result.runtime_state_ref)
        if invocation.output_contract == "research_claim":
            return self._record_candidate(
                state,
                spec,
                invocation,
                result,
                runtime_name=runtime_name,
            )
        engine._append(
            state,
            "independent_analysis",
            "invocation",
            invocation.agent_id,
            "Agent invocation completed",
            {
                "runtime": runtime_name,
                "agent_id": invocation.agent_id,
                "status": result.status,
                "error": result.error,
                "source_refs": source_refs,
                "invocation_id": invocation.invocation_id,
                "attempt": invocation.attempt,
                "retry_of": invocation.retry_of,
            },
        )
        fields = {
            field: result.structured_output[field]
            for field in ("statement", "boundary", "prediction", "falsification_condition")
        }
        payload = {
            **fields,
            "role": invocation.role,
            "agent_id": invocation.agent_id,
            "runtime": runtime_name,
            "status": result.status,
            "error": result.error,
            "source": "live",
            "source_refs": source_refs,
        }
        claim_step = engine._append(
            state,
            "independent_analysis",
            "claim",
            invocation.agent_id,
            result.content,
            payload,
        )
        previous = state.memory.latest("Claim", object_key=invocation.agent_id)
        state.memory.append(
            "Claim",
            {"agent_id": invocation.agent_id, **fields, "status": "initial", "cycle": state.cycle, "source": "live"},
            supersedes=previous.id if previous else None,
            object_key=invocation.agent_id,
        )
        timestamp = time.time()
        agent_name = str(spec.get("name") or invocation.agent_id)
        artifact_id = f"artifact:{state.run_id}:{state.cycle}:{invocation.agent_id}"
        artifact = {
            "artifact_id": artifact_id,
            "run_id": state.run_id,
            "group_chat_id": state.group_chat_id,
            "agent_id": invocation.agent_id,
            "artifact_type": "master_research_markdown",
            "filename": master_artifact_filename(
                timestamp=timestamp,
                task_name=str(state.task_context.get("initial_intent") or "独立分析"),
                agent_name=agent_name,
            ),
            "content": build_master_markdown(
                agent_name=agent_name,
                agent_id=invocation.agent_id,
                topic_name=str(state.task_context.get("topic_name") or "泥浆基泡沫混凝土"),
                initial_intent=str(state.task_context.get("initial_intent", "")),
                content=result.content,
                fields=fields,
                runtime=runtime_name,
                profile_version=invocation.profile_version,
                instruction_version=invocation.agent_instruction.instruction_version if invocation.agent_instruction else "",
                data_space=invocation.data_space,
            ),
            "data_space": invocation.data_space,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        state.persist_artifact(artifact)
        claim_step.payload["artifact_id"] = artifact_id
        claim_step.payload["source_refs"] = [*source_refs, artifact_id]
        state.persist()
        return True

    def _record_candidate(
        self,
        state: RunState,
        spec: dict,
        invocation: AgentInvocation,
        result: AgentResult,
        *,
        runtime_name: str,
    ) -> bool:
        from app.orchestration import engine

        output = dict(result.structured_output)
        source_refs = [
            *invocation.input_refs,
            *[
                str(ref)
                for ref in output.get("evidence_refs", [])
                if isinstance(ref, str) and ref.strip()
            ],
        ]
        engine._append(
            state,
            "independent_analysis",
            "invocation",
            invocation.agent_id,
            "Agent invocation completed",
            {
                "runtime": runtime_name,
                "agent_id": invocation.agent_id,
                "task_id": invocation.task_id,
                "document_scope": list(invocation.document_scope),
                "status": result.status,
                "error": result.error,
                "source_refs": source_refs,
                "invocation_id": invocation.invocation_id,
                "attempt": invocation.attempt,
                "retry_of": invocation.retry_of,
            },
        )
        candidate = self._candidate_writer(state, invocation, result) if self._candidate_writer else None
        candidate_id = ""
        if candidate is not None:
            if isinstance(candidate, Mapping):
                candidate_id = str(candidate.get("candidate_id", ""))
            else:
                candidate_id = str(getattr(candidate, "candidate_id", ""))
            if candidate_id:
                state.candidate_ids.append(candidate_id)
        state.task_context.setdefault("candidate_results", []).append({
            "agent_id": invocation.agent_id,
            "task_id": invocation.task_id,
            "document_scope": list(invocation.document_scope),
            "runtime": runtime_name,
            "data_space": invocation.data_space,
            "status": result.status,
            "content": result.content,
            "structured_output": output,
            "candidate_id": candidate_id,
            "source_refs": source_refs,
        })
        engine._append(
            state,
            "independent_analysis",
            "candidate",
            invocation.agent_id,
            result.content,
            {
                **output,
                "runtime": runtime_name,
                "agent_id": invocation.agent_id,
                "task_id": invocation.task_id,
                "document_scope": list(invocation.document_scope),
                "status": result.status,
                "source": "live",
                "source_refs": source_refs,
                **({"candidate_id": candidate_id} if candidate_id else {}),
            },
        )
        state.persist()
        return True

    async def _run_review(
        self,
        state: RunState,
        runtime: object,
        runtime_name: str,
        topic_context: dict,
        context_factory: Callable,
        outcome: MultiAgentRunResult,
    ) -> ReviewGateResult | None:
        spec = dict(state.review_agent_spec)
        invocation = self._build_invocation(
            state,
            spec,
            phase="review_gate",
            topic_context=topic_context,
            task="审查所有硕士候选观点，检查反例、可推翻条件和缺失观察，并给出是否通过审查门的建议",
            input_refs=[
                step.id
                for step in state.steps
                if step.kind in {"claim", "candidate"}
                and step.phase == "independent_analysis"
                and step.payload.get("source") == "live"
            ],
        )
        review = await self._invoke(
            state,
            runtime,
            runtime_name,
            invocation,
            context_factory,
            outcome,
        )
        if review is None:
            return None
        raw_items = normalize_review_items(review.structured_output)
        if raw_items is None:
            self._fail(state, review.agent_id, "review_gate", "博士 review_gate 必须返回 items 或审查分类数组", runtime_name=runtime_name, invocation=invocation)
            return None
        items: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict) or not isinstance(item.get("content"), str) or not item["content"].strip():
                self._fail(state, review.agent_id, "review_gate", "博士 review_gate 的审查意见不能为空", runtime_name=runtime_name, invocation=invocation)
                return None
            if item.get("kind") not in {"counterexample", "falsification_condition", "missing_observation"}:
                self._fail(state, review.agent_id, "review_gate", "博士 review_gate 的 kind 不符合审查契约", runtime_name=runtime_name, invocation=invocation)
                return None
            items.append({"kind": item["kind"], "content": item["content"].strip()})
        kinds = {item["kind"] for item in items}
        required = {"counterexample", "falsification_condition", "missing_observation"}
        if kinds != required:
            self._fail(state, review.agent_id, "review_gate", "博士 review_gate 必须覆盖反例、可推翻条件和缺失观察", runtime_name=runtime_name, invocation=invocation)
            return None
        try:
            review_result = ReviewGateResult(
                reviewed_candidate_ids=[item["agent_id"] for item in self._claim_context(state)],
                counterexamples=[item["content"] for item in items if item["kind"] == "counterexample"],
                falsification_conditions=[
                    item["content"]
                    for item in items
                    if item["kind"] == "falsification_condition"
                ],
                missing_evidence=[item["content"] for item in items if item["kind"] == "missing_observation"],
                disposition=str(review.structured_output.get("disposition", "approved")),
            )
        except Exception as exc:
            self._fail(
                state,
                review.agent_id,
                "review_gate",
                f"博士 review_gate 结果无效: {exc}",
                runtime_name=runtime_name,
                invocation=invocation,
            )
            return None
        from app.orchestration import engine

        for item in items:
            engine._append(
                state,
                "review_gate",
                "review_opinion",
                review.agent_id,
                item["content"],
                {**item, "source": "live", "runtime": runtime_name, "agent_id": review.agent_id, "role": "phd_student"},
            )
        state.review_result = review_result.model_dump(mode="json")
        if state.task_context.get("completion_mode") != "candidate_review":
            state.memory.append("ReviewGate", {**state.review_result, "source": "live", "agent_id": review.agent_id})
        state.persist()
        outcome.reviewer = review_result
        if review_result.disposition != "approved":
            self._fail(
                state,
                review.agent_id,
                "review_gate",
                f"博士审查门未通过: {review_result.disposition}",
                status=review_result.disposition,
                runtime_name=runtime_name,
                invocation=invocation,
            )
            return review_result
        # Task-scoped runs expose a separate invocation audit step. The
        # Scenario-backed compatibility path keeps its established three
        # review-opinion steps so existing meeting projections remain stable.
        if state.task_context.get("completion_mode") == "candidate_review":
            self._record_invocation_outcome(state, invocation, review, runtime_name=runtime_name)
        return review_result

    async def _run_postdoc(
        self,
        state: RunState,
        runtime: object,
        runtime_name: str,
        topic_context: dict,
        context_factory: Callable,
        outcome: MultiAgentRunResult,
    ) -> PostdocSynthesis | None:
        from app.orchestration import engine

        spec = dict(state.postdoc_agent_spec)
        domain = str(spec.get("specialty_domain") or "授权专业范围")
        input_refs = [
            step.id
            for step in state.steps
            if step.phase == "review_gate"
            or (step.kind in {"claim", "candidate"} and step.phase == "independent_analysis")
        ]
        request = engine._append(
            state,
            "postdoc_exchange",
            "request",
            str(spec.get("agent_id", "postdoc")),
            f"专业请求：请在 {domain} 范围内综合当前候选观点",
            {
                "source": "live",
                "runtime": runtime_name,
                "agent_id": str(spec.get("agent_id", "postdoc")),
                "role": "postdoc",
                "domain": domain,
                "source_refs": list(input_refs),
            },
        )
        input_refs = [*input_refs, request.id]
        invocation = self._build_invocation(
            state,
            spec,
            phase="postdoc_exchange",
            topic_context=topic_context,
            task=f"专业范围：{domain}。综合硕士候选和博士审查意见，给出范围内的专业摘要、建议、限制和未决问题",
            input_refs=input_refs,
        )
        response = await self._invoke(
            state,
            runtime,
            runtime_name,
            invocation,
            context_factory,
            outcome,
        )
        if response is None:
            return None
        try:
            synthesis = PostdocSynthesis.model_validate(response.structured_output)
        except Exception as exc:
            self._fail(
                state,
                response.agent_id,
                "postdoc_exchange",
                f"博士后综合结果无效: {exc}",
                runtime_name=runtime_name,
                invocation=invocation,
            )
            return None
        self._record_invocation_outcome(state, invocation, response, runtime_name=runtime_name)
        step = engine._append(
            state,
            "postdoc_exchange",
            "synthesis",
            response.agent_id,
            response.content,
            {
                **synthesis.model_dump(mode="json"),
                "source": "live",
                "runtime": runtime_name,
                "agent_id": response.agent_id,
                "source_refs": list(invocation.input_refs),
            },
        )
        state.postdoc_result = synthesis.model_dump(mode="json")
        if state.task_context.get("completion_mode") != "candidate_review":
            state.memory.append(
                "PostdocSynthesis",
                {**state.postdoc_result, "source": "live", "agent_id": response.agent_id, "source_refs": [step.id]},
            )
        state.pi_suggestion = {
            "option": "pending",
            "reason": synthesis.summary,
            "source": "live",
            "source_refs": [step.id],
            "generated_by": response.agent_id,
        }
        state.persist()
        outcome.postdoc = synthesis
        return synthesis

    @staticmethod
    def _record_invocation_outcome(
        state: RunState,
        invocation: AgentInvocation,
        result: AgentResult,
        *,
        runtime_name: str,
    ) -> None:
        from app.orchestration import engine

        source_refs = list(invocation.input_refs)
        if result.runtime_state_ref:
            source_refs.append(result.runtime_state_ref)
        engine._append(
            state,
            invocation.phase,
            "invocation",
            invocation.agent_id,
            "Agent invocation completed",
            {
                "runtime": runtime_name,
                "agent_id": invocation.agent_id,
                "task_id": invocation.task_id,
                "document_scope": list(invocation.document_scope),
                "status": result.status,
                "error": result.error,
                "source_refs": source_refs,
                "invocation_id": invocation.invocation_id,
                "attempt": invocation.attempt,
                "retry_of": invocation.retry_of,
            },
        )

    def _fail(
        self,
        state: RunState,
        agent_id: str,
        phase: str,
        error: str,
        *,
        status: str = "error",
        runtime_name: str | None = None,
        invocation: AgentInvocation | None = None,
    ) -> None:
        from app.orchestration import engine

        engine._fail_live(
            state,
            agent_id=agent_id,
            runtime=runtime_name or state.runtime_name or "unavailable",
            error=error,
            status=status,
            phase=phase,
            invocation_id=invocation.invocation_id if invocation else None,
            attempt=invocation.attempt if invocation else None,
            retry_of=invocation.retry_of if invocation else None,
            meeting_service=self._meeting_service,
        )
