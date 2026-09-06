"""Pi client contract and transport errors."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Protocol, runtime_checkable


PiRequest = dict[str, object]
PiRawResult = dict[str, object]


def normalize_pi_response(raw: object) -> PiRawResult:
    """Normalize legacy final mappings and the internal tool envelope."""
    if not isinstance(raw, Mapping):
        raise PiProtocolError("Pi response must be an object")
    value = dict(raw)
    envelope = value.get("type", value.get("envelope", value.get("kind")))
    if envelope is None:
        envelope = "final"
    if envelope == "final":
        content = value.get("content", "")
        if not isinstance(content, str):
            raise PiProtocolError("final content must be text")
        value["type"] = "final"
        return value
    if envelope != "tool_request":
        raise PiProtocolError("unknown Pi response envelope")
    request_id = value.get("request_id")
    name = value.get("name")
    arguments = value.get("arguments", {})
    input_refs = value.get("input_refs", [])
    data_space = value.get("data_space", "synthetic")
    if not isinstance(request_id, str) or not request_id.strip():
        raise PiProtocolError("tool request request_id must be non-empty text")
    if not isinstance(name, str) or not name.strip():
        raise PiProtocolError("tool request name must be non-empty text")
    if not isinstance(arguments, Mapping):
        raise PiProtocolError("tool request arguments must be an object")
    if not isinstance(input_refs, list) or not all(isinstance(ref, str) for ref in input_refs):
        raise PiProtocolError("tool request input_refs must be a list of strings")
    if not isinstance(data_space, str) or not data_space.strip():
        raise PiProtocolError("tool request data_space must be non-empty text")
    return {
        "type": "tool_request", "request_id": request_id, "name": name,
        "arguments": deepcopy(dict(arguments)), "input_refs": list(input_refs), "data_space": data_space,
    }


def build_tool_follow_up(request: Mapping[str, object], tool_result: Mapping[str, object] | object) -> PiRequest:
    """Add a serialized ToolResult to the next Pi request without executing it."""
    follow_up = deepcopy(dict(request))
    existing = follow_up.get("tool_results", [])
    if not isinstance(existing, list):
        raise PiProtocolError("tool_results must be a list")
    if hasattr(tool_result, "model_dump"):
        serialized = tool_result.model_dump(mode="json")
    elif isinstance(tool_result, Mapping):
        serialized = deepcopy(dict(tool_result))
    else:
        raise PiProtocolError("tool result must be an object")
    follow_up["tool_results"] = existing + [serialized]
    return follow_up


@runtime_checkable
class PiClient(Protocol):
    """Transport-neutral contract for one Pi Agent invocation."""

    async def invoke(self, request: PiRequest) -> PiRawResult:
        """Send one controlled request and return the raw runtime result."""
        ...


class PiClientError(RuntimeError):
    """Base error for Pi client failures."""


class PiTimeoutError(PiClientError):
    """Pi did not finish within the configured timeout."""


class PiAuthError(PiClientError):
    """Pi or its model provider rejected authentication."""


class PiProtocolError(PiClientError):
    """Pi returned a response that does not match the client contract."""


class PiUnavailableError(PiClientError):
    """Pi could not be reached or started."""
