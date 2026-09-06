"""Read-only tool contracts. These DTOs contain no execution or data-store access."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _non_empty(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be non-empty text")
    return value.strip()


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    description: str
    read_only: bool
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_roles: list[str] = Field(min_length=1)
    allowed_phases: list[str] = Field(min_length=1)
    data_spaces: list[str] = Field(min_length=1)
    result_data_spaces: list[str] | None = None
    result_limits: dict[str, int] = Field(default_factory=dict)

    _text_fields = field_validator("name", "version", "description", mode="before")(_non_empty)

    @model_validator(mode="after")
    def enforce_read_only_contract(self) -> "ToolSpec":
        if not self.read_only:
            raise ValueError("P2 tools must be read-only")
        if any(not isinstance(item, str) or not item.strip() for items in (
            self.allowed_roles, self.allowed_phases, self.data_spaces
        ) for item in items):
            raise ValueError("role, phase and data space constraints must be non-empty")
        if any(value < 0 for value in self.result_limits.values()):
            raise ValueError("result limits must be non-negative")
        if self.result_data_spaces is None:
            self.result_data_spaces = list(self.data_spaces)
        if any(not isinstance(item, str) or not item.strip() for item in self.result_data_spaces):
            raise ValueError("result data spaces must be non-empty")
        return self


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    data_space: str = "synthetic"
    input_refs: list[str] = Field(default_factory=list)

    _text_fields = field_validator("request_id", "name", "data_space", mode="before")(_non_empty)


ToolResultStatus = Literal["ok", "denied", "error", "limit_exceeded"]


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    name: str
    version: str
    status: ToolResultStatus = "ok"
    payload: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    data_space: str = "synthetic"
    error_code: str | None = None
    boundary_notes: list[str] = Field(default_factory=list)

    _text_fields = field_validator("request_id", "name", "version", "data_space", mode="before")(_non_empty)


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    request_id: str
    run_id: str
    group_chat_id: str
    cycle: int | None = None
    phase: str
    agent_id: str
    role: str
    runtime: str
    tool_name: str
    tool_version: str
    authorization: Literal["allowed", "denied"]
    status: Literal["success", "rejected", "error", "limit_exceeded"]
    argument_summary: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    requested_data_space: str = "synthetic"
    returned_data_space: str | None = "synthetic"
    policy_version: str
    error_code: str | None = None
    error_message: str = ""
    started_at: float
    duration_ms: float = Field(ge=0)

    @property
    def data_space(self) -> str:
        """Convenience view for callers that only need the returned space."""
        return self.returned_data_space or self.requested_data_space

    _text_fields = field_validator(
        "record_id", "request_id", "run_id", "group_chat_id", "phase", "agent_id",
        "role", "runtime", "tool_name", "tool_version", "requested_data_space", "policy_version",
        mode="before",
    )(_non_empty)


class ToolPolicyDecision(BaseModel):
    allowed: bool
    reason: str
    policy_version: str = "p2-v1"
    allowed_tools: list[str] = Field(default_factory=list)

    _text_fields = field_validator("reason", "policy_version", mode="before")(_non_empty)
