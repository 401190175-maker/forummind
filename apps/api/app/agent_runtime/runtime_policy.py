"""Runtime 选择策略：解释 API mode 与环境配置，不创建 runtime。"""

from __future__ import annotations

import os
from collections.abc import Mapping

from app.agent_runtime.config import runtime_config
from app.agent_runtime.schemas import RuntimeSelection

_SUPPORTED_RUNTIMES = {"legacy_llm", "mock", "pi"}
_DEFAULT_RUNTIME = "legacy_llm"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _pi_configuration_error(values: Mapping[str, str]) -> str:
    """Return the first missing Pi prerequisite, or an empty string."""
    if values.get("PI_ENABLED", "").strip().lower() not in _TRUE_VALUES:
        return "PI_ENABLED is not enabled"
    if not values.get("PI_MODEL", "").strip():
        return "PI_MODEL is not configured"
    if values.get("PI_RUNTIME_URL", "").strip():
        if not values.get("PI_RUNTIME_TOKEN", "").strip():
            return "PI_RUNTIME_TOKEN is not configured"
        return ""
    if not (
        values.get("PI_BASE_URL", "").strip()
        or values.get("PI_API_KEY", "").strip()
    ):
        return "PI_BASE_URL or PI_API_KEY is not configured"
    return ""


def resolve_runtime_policy(
    api_mode: str,
    env: Mapping[str, str] | None = None,
    *,
    require_pi: bool = False,
) -> RuntimeSelection:
    """返回 Run API 与 runtime factory 之间的轻量选择结果。"""

    if api_mode not in {"auto", "live", "replay"}:
        raise ValueError(f"unsupported run mode: {api_mode}")

    if api_mode == "replay":
        return RuntimeSelection(api_mode="replay", resolved_mode="replay")

    values: Mapping[str, str]
    if env is not None:
        values = env
    else:
        configured = runtime_config.current()
        if configured is None:
            values = os.environ
        else:
            values = dict(os.environ)
            values.update(
                {
                    "AGENT_RUNTIME": "pi",
                    "PI_ENABLED": "true",
                    "PI_MODEL": configured.model,
                    "PI_BASE_URL": configured.base_url,
                }
            )
    configured_runtime = values.get("AGENT_RUNTIME", "").strip()

    if api_mode in {"auto", "live"}:
        if configured_runtime != "pi":
            configured = configured_runtime or "<empty>"
            reason = f"AGENT_RUNTIME is not set to pi (got {configured})"
        else:
            reason = _pi_configuration_error(values)
        if reason:
            warning = f"Pi runtime is unavailable: {reason}"
            return RuntimeSelection(
                api_mode=api_mode,
                resolved_mode="live",
                runtime_name="unavailable",
                fallback_reason=warning,
                warnings=[warning],
            )
        return RuntimeSelection(
            api_mode=api_mode,
            resolved_mode="live",
            runtime_name="pi",
        )
    raise AssertionError(f"unhandled API mode: {api_mode}")
