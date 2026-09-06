"""Runtime factory：按显式选择创建 Agent Runtime。"""

from __future__ import annotations

import os
from collections.abc import Callable

from app.agent_runtime.base import AgentRuntime
from app.agent_runtime.config import runtime_config
from app.agent_runtime.legacy_llm_runtime import LegacyLLMRuntime
from app.agent_runtime.mock_runtime import MockRuntime
from app.agent_runtime.pi_http_client import HttpPiClient
from app.agent_runtime.native_pi_client import NativePiClient
from app.agent_runtime.pi_runtime import PiRuntime
from app.agent_runtime.schemas import RuntimeSelection
from app.tools.context import ToolExecutionContext
from app.tools.registry import ToolRegistry

_AGENT_RUNTIME_ENV = "AGENT_RUNTIME"
_DEFAULT_RUNTIME = "legacy_llm"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _pi_configuration_error() -> str:
    configured = runtime_config.current()
    if configured is not None:
        if not configured.model:
            return "PI_MODEL is not configured"
        if not (configured.base_url or configured.api_key or os.getenv("PI_RUNTIME_URL", "").strip()):
            return "PI_BASE_URL or PI_API_KEY is not configured"
        return ""
    if os.getenv("PI_ENABLED", "").strip().lower() not in _TRUE_VALUES:
        return "PI_ENABLED is not enabled"
    if not os.getenv("PI_MODEL", "").strip():
        return "PI_MODEL is not configured"
    if os.getenv("PI_RUNTIME_URL", "").strip():
        if not os.getenv("PI_RUNTIME_TOKEN", "").strip():
            return "PI_RUNTIME_TOKEN is not configured"
        return ""
    if not (
        os.getenv("PI_BASE_URL", "").strip()
        or os.getenv("PI_API_KEY", "").strip()
    ):
        return "PI_BASE_URL or PI_API_KEY is not configured"
    return ""


def _pi_timeout() -> float:
    try:
        return max(float(os.getenv("PI_TIMEOUT_SECONDS", "60")), 0.1)
    except ValueError:
        return 60.0


def _pi_native_prompt_timeout(request_timeout: float) -> float:
    try:
        sidecar_timeout = max(float(os.getenv("PI_PROMPT_TIMEOUT_MS", "300000")) / 1000, 0.1)
    except ValueError:
        sidecar_timeout = 300.0
    return max(request_timeout, sidecar_timeout + 5.0)


def create_runtime(
    runtime_name: str | RuntimeSelection | AgentRuntime | None = None,
    *,
    tool_registry: ToolRegistry | None = None,
    context_factory: Callable | None = None,
) -> AgentRuntime | None:
    """创建 Agent Runtime。

    回退策略由 runtime policy 决定；factory 只按明确名称创建。
    """
    implicit_environment_selection = False
    if isinstance(runtime_name, RuntimeSelection):
        if runtime_name.resolved_mode == "replay":
            return None
        name = runtime_name.runtime_name
    elif isinstance(runtime_name, str) or runtime_name is None:
        implicit_environment_selection = runtime_name is None
        name = (runtime_name or os.getenv(_AGENT_RUNTIME_ENV, _DEFAULT_RUNTIME)).strip()
        if not name:
            name = _DEFAULT_RUNTIME
    elif hasattr(runtime_name, "invoke"):
        return runtime_name
    else:
        raise ValueError(f"unsupported runtime selection: {runtime_name!r}")

    if name == "unavailable":
        return None
    if name == "legacy_llm":
        return LegacyLLMRuntime()
    if name == "mock":
        return MockRuntime()
    if name == "pi":
        if _pi_configuration_error():
            return None
        configured = runtime_config.current()
        native_url = os.getenv("PI_RUNTIME_URL", "").strip()
        native_token = os.getenv("PI_RUNTIME_TOKEN", "").strip()
        base_url = configured.base_url if configured is not None else os.getenv("PI_BASE_URL", "")
        api_key = configured.api_key if configured is not None else os.getenv("PI_API_KEY", "")
        model = configured.model if configured is not None else os.getenv("PI_MODEL", "")
        provider = configured.provider if configured is not None else os.getenv("PI_PROVIDER", "pi")
        protocol = "pi" if provider.strip().lower() in {"pi", "pi-sidecar", "sidecar"} else "openai_compatible"
        request_timeout = _pi_timeout()
        client = (
            NativePiClient(
                native_url,
                native_token,
                timeout=request_timeout,
                prompt_timeout=_pi_native_prompt_timeout(request_timeout),
            )
            if native_url else HttpPiClient(
                base_url=base_url, api_key=api_key, protocol=protocol, timeout=request_timeout
            )
        )
        return PiRuntime(
            client,
            model=model,
            tool_registry=tool_registry,
            context_factory=context_factory,
        )
    if implicit_environment_selection:
        return LegacyLLMRuntime()
    raise ValueError(f"unknown agent runtime: {name}")
