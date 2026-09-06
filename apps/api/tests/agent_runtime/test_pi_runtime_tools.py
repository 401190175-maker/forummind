import asyncio

from app.agent_runtime.pi_runtime import PiRuntime
from app.agent_runtime.schemas import AgentInvocation
from app.tools import build_synthetic_registry
from app.tools.context import build_tool_execution_context


def _invocation(**updates):
    return AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student",
        task="inspect", allowed_tools=["memory.query", "literature.search", "experiment.analyze_demo"],
        input_refs=[], output_contract="claim_four_fields",
    ).model_copy(update=updates)


class FakePi:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _context(invocation):
    return build_tool_execution_context(invocation, runtime_name="pi", memory_entries=[
        {"id": "mem-1", "kind": "Claim", "payload": {"statement": "pore"}, "version": 1, "data_space": "synthetic"}
    ])


def test_pi_runtime_runs_authorized_tool_and_returns_final_candidate() -> None:
    pi = FakePi([
        {"type": "tool_request", "request_id": "r-1", "name": "memory.query", "arguments": {"kind": "Claim"}},
        {"type": "final", "agent_id": "agent-ms-1", "content": "claim", "structured_output": {
            "statement": "claim", "boundary": "b", "prediction": "p", "falsification_condition": "f"
        }},
    ])
    registry = build_synthetic_registry()
    result = asyncio.run(PiRuntime(pi, registry, _context).invoke(_invocation()))
    assert result.status == "ok" and result.content == "claim"
    assert result.tool_calls[0]["tool_name"] == "memory.query"
    assert pi.requests[0]["tool_specs"][0]["name"] == "memory.query"
    assert pi.requests[1]["tool_results"][0]["status"] == "ok"


def test_pi_runtime_stops_unbounded_tool_requests() -> None:
    pi = FakePi([
        {"type": "tool_request", "request_id": f"r-{i}", "name": "memory.query", "arguments": {}}
        for i in range(5)
    ])
    registry = build_synthetic_registry()
    result = asyncio.run(PiRuntime(pi, registry, _context).invoke(_invocation()))
    assert result.status == "error" and "limit" in result.error
    assert len(pi.requests) == 4
    assert len(registry.audit("run-1")) == 4
    assert registry.audit("run-1")[-1].status == "limit_exceeded"


def test_pi_runtime_without_dependencies_does_not_expose_tools() -> None:
    pi = FakePi([{"content": "plain", "structured_output": {}}])
    result = asyncio.run(PiRuntime(pi).invoke(_invocation()))
    assert result.status == "ok" and "tool_specs" not in pi.requests[0]


def test_pi_runtime_enforces_the_invocation_tool_allowlist() -> None:
    pi = FakePi([
        {
            "type": "tool_request",
            "request_id": "r-foreign",
            "name": "literature.search",
            "arguments": {"query": "not allowed"},
        },
    ])
    registry = build_synthetic_registry()
    invocation = _invocation(allowed_tools=["memory.query"])

    result = asyncio.run(PiRuntime(pi, registry, _context).invoke(invocation))

    assert result.status == "error"
    assert result.error_code == "pi_tool_not_allowed"
    assert [spec["name"] for spec in pi.requests[0]["tool_specs"]] == [
        "memory.query"
    ]
    assert registry.audit("run-1") == []
