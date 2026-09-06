import pytest

from app.agent_runtime.pi_client import (
    PiProtocolError,
    build_tool_follow_up,
    normalize_pi_response,
)


def test_protocol_normalizes_legacy_final_and_tool_request() -> None:
    final = normalize_pi_response({"content": "claim", "structured_output": {}})
    assert final["type"] == "final" and final["content"] == "claim"
    request = normalize_pi_response({
        "type": "tool_request", "request_id": "r-1", "name": "memory.query",
        "arguments": {"kind": "Claim"}, "input_refs": ["mem-1"],
    })
    assert request == {"type": "tool_request", "request_id": "r-1", "name": "memory.query",
                       "arguments": {"kind": "Claim"}, "input_refs": ["mem-1"], "data_space": "synthetic"}


def test_follow_up_carries_result_as_protocol_data_only() -> None:
    result = {"request_id": "r-1", "name": "memory.query", "status": "ok", "payload": {"items": []}}
    follow_up = build_tool_follow_up({"task": "inspect", "tool_results": []}, result)
    assert follow_up["tool_results"] == [result]
    result["payload"]["items"].append("changed")
    assert follow_up["tool_results"][0]["payload"]["items"] == []


@pytest.mark.parametrize("raw", [None, [], {"type": "unknown"}, {"type": "tool_request", "name": "x"},
                                  {"type": "tool_request", "request_id": "r", "name": "x", "arguments": []}])
def test_protocol_rejects_malformed_envelopes(raw) -> None:
    with pytest.raises(PiProtocolError):
        normalize_pi_response(raw)
