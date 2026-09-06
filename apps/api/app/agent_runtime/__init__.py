"""Agent Runtime Adapter 包（design.md §2.6，Pi 接入 Phase 1）。

本包统一封装单个 Agent 的执行边界：

- `schemas.py`：运行时 DTO（`AgentInvocation` / `AgentResult` /
  `RuntimeSelection` / `CandidateStreamEvent`），第一阶段不升级为持久化
  domain schema。
- `mock_runtime.py`：测试用 runtime，不访问外部服务。
- 后续子模块：`base.py` / `replay_runtime.py` / `legacy_llm_runtime.py` /
  `factory.py` / `candidate_buffer.py` / `pi_runtime.py`（后续阶段）。

边界约定：

- runtime 只负责“单个 Agent 怎么运行”，不负责阶段推进、审查门、
  冻结、Memory 正式写入或 PI 裁决（design §1.3）。
- 本包不导入 FastAPI，不访问数据库、文件系统或 LLM。
"""

from app.agent_runtime.schemas import (
    AgentInstruction,
    AgentInvocation,
    AgentResult,
    CandidateStreamEvent,
    RuntimeSelection,
    RuntimeEvent,
    RuntimeSessionRef,
    ReviewGateResult,
    PostdocSynthesis,
)
from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.runtime_policy import resolve_runtime_policy

__all__ = [
    "AgentInstruction",
    "AgentInvocation",
    "AgentResult",
    "RuntimeSelection",
    "RuntimeEvent",
    "RuntimeSessionRef",
    "ReviewGateResult",
    "PostdocSynthesis",
    "CandidateStreamEvent",
    "MockRuntime",
    "resolve_runtime_policy",
]
