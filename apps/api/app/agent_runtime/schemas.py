"""Agent Runtime Adapter DTO（design.md §4.5，tasks.md Task 18）。

- `AgentInvocation`：ForumMind 发给 runtime 的单次 Agent 任务包。
- `AgentResult`：runtime 返回的候选结果，必须经 ForumMind 校验后才可
  写入正式对象（正式 Memory 仍由 orchestration 控制）。
- `RuntimeSelection`：runtime policy 与 factory 之间的轻量选择结果。
- `CandidateStreamEvent`：Pi/live streaming 的候选流事件，默认未校验；
  只有显式操作才能升级为 `validated` / `rejected`。

边界约定：

- 本模块只定义 Pydantic DTO，不导入 FastAPI、不访问 LLM、
  不访问数据库或文件系统。
- 默认 `data_space = "synthetic"`。
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.tasks.schemas import DatasetVersionRef


class AgentInstruction(BaseModel):
    """Deterministic, serializable system instruction for one Agent call."""

    instruction_version: str = "agent-instruction-v1"
    profile_version: str = ""
    agent_id: str
    role: str
    identity: str
    description: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    primary_ability: str | None = None
    secondary_abilities: list[str] = Field(default_factory=list)
    general_research_abilities: list[str] = Field(default_factory=list)
    allowed_data_spaces: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    specialty_domain: str | None = None
    knowledge_base_coverage: str | None = None
    forbidden_actions: str | None = None
    topic_context: dict = Field(default_factory=dict)
    task_context: dict = Field(default_factory=dict)
    phase: str = ""
    phase_rules: list[str] = Field(default_factory=list)
    output_contract: str = "free_text"
    safety_rules: list[str] = Field(default_factory=list)

    def render(self) -> str:
        """Render a stable system message without hidden runtime state."""
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "ForumMind AgentInstruction\n" + payload


class AgentInvocation(BaseModel):
    """ForumMind 发给 Agent Runtime 的单次任务包（design §4.5）。"""

    invocation_id: str = Field(default_factory=lambda: f"inv-{uuid.uuid4().hex}")
    attempt: int = Field(default=1, ge=1)  # 同一 Agent 的第几次尝试
    retry_of: str = ""  # 失败 invocation 的 ID；首次调用为空
    run_id: str = ""  # 所属 run，Phase 1 兼容旧调用
    group_chat_id: str = ""  # 所属课题组群聊
    cycle: int | None = None  # 当前科研循环
    phase: str = ""  # 当前阶段（如 independent_analysis）
    agent_id: str  # Agent 标识（如 agent-ms-1）
    role: str  # 科研角色（master_student / phd_student / postdoc）
    profile_version: str = ""  # 冻结的 AgentProfile 版本
    agent_instruction: AgentInstruction | None = None  # 显式 system instruction
    task: str  # 任务描述（prompt）
    input_refs: list[str] = Field(default_factory=list)  # 输入对象引用
    context: dict = Field(default_factory=dict)  # 最小上下文（只读快照）
    allowed_tools: list[str] = Field(default_factory=list)  # 工具白名单
    output_contract: str = "free_text"  # 输出契约（自由文本 / 结构化 schema 名）
    data_space: str = "synthetic"  # 数据空间，默认 synthetic
    task_id: str = ""  # 真实研究任务身份；synthetic 兼容调用可为空
    document_scope: list[str] = Field(default_factory=list)  # 服务端冻结的文档范围
    dataset_refs: list[DatasetVersionRef] = Field(default_factory=list)
    safety_rules: list[str] = Field(default_factory=list)  # 不可越过的规则


class AgentResult(BaseModel):
    """Runtime 返回的候选结果（design §4.5）。

    `status`：`ok` 正常 / `fallback` 降级结果 / `error` 调用失败。
    结果只是候选：是否写入 RunStep / Memory 由 orchestration 决定。
    """

    agent_id: str = ""  # 输出归属
    status: Literal["ok", "fallback", "error"]
    content: str  # 文本输出
    structured_output: dict = Field(default_factory=dict)  # 结构化输出
    tool_calls: list[dict] = Field(default_factory=list)  # 工具调用审计占位
    runtime_state_ref: str = ""  # 外部 runtime 短期 state 引用
    warnings: list[str] = Field(default_factory=list)  # 警告列表
    error: str = ""  # 致命失败详情
    error_code: str = ""  # 可供服务层分类的稳定错误码
    data_space: str = "synthetic"  # 数据空间，默认 synthetic


class ReviewGateResult(BaseModel):
    """Validated PhD review outcome; it is not a PI decision."""

    reviewed_candidate_ids: list[str] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)
    falsification_conditions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    disposition: Literal["approved", "needs_revision", "rejected"] = "approved"


class PostdocSynthesis(BaseModel):
    """Professional synthesis candidate, kept separate from formal decisions."""

    summary: str
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class RuntimeEvent(BaseModel):
    """Normalized event envelope projected from the native Node runtime."""

    event_id: str
    cursor: int = Field(ge=1)
    session_id: str
    invocation_id: str
    run_id: str
    group_chat_id: str
    agent_id: str
    phase: str
    type: Literal[
        "run_started", "agent_started", "text_delta", "text_completed", "tool_started",
        "tool_update", "tool_completed", "turn_started", "turn_completed",
        "agent_settled", "agent_failed", "agent_aborted",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    data_space: str = "synthetic"
    task_id: str = ""
    document_scope: list[str] = Field(default_factory=list)
    timestamp: float


class RuntimeSessionRef(BaseModel):
    session_id: str
    group_chat_id: str
    run_id: str
    agent_id: str
    phase: str
    data_space: str = "synthetic"
    task_id: str = ""
    document_scope: list[str] = Field(default_factory=list)
    status: str = "active"
    last_cursor: int = Field(default=0, ge=0)
    invocation_id: str = ""
    attempt: int = Field(default=1, ge=1)
    retry_of: str = ""


class RuntimeSelection(BaseModel):
    """Runtime policy 的选择结果，不创建 runtime、不发起模型调用。"""

    api_mode: Literal["auto", "live", "replay"]
    resolved_mode: Literal["live", "replay"]
    runtime_name: Literal["legacy_llm", "mock", "pi", "unavailable", ""] = ""
    fallback_reason: str = ""
    warnings: list[str] = Field(default_factory=list)


class CandidateStreamEvent(BaseModel):
    """Pi/live streaming 候选流事件（design §4.5、§8.6）。

    `status`：`streaming` / `completed` 为初始状态；只有显式调用
    candidate buffer 的 `mark_validated` / `mark_rejected` 才可变为
    `validated` / `rejected`。未校验内容不能成为正式群聊消息、
    正式产物或正式 Memory。
    """

    id: str  # 事件 ID（稳定唯一）
    run_id: str  # 所属 run
    agent_id: str  # 产生事件的 Agent
    content_delta: str  # 内容增量
    status: Literal["streaming", "completed", "validated", "rejected"]
    data_space: str = "synthetic"  # 数据空间，默认 synthetic
    task_id: str = ""
    document_scope: list[str] = Field(default_factory=list)
