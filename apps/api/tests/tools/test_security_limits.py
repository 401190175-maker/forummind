from app.agent_runtime.schemas import AgentInvocation
from app.tools import build_synthetic_registry
from app.tools.context import ToolLimits, build_tool_execution_context
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolRequest, ToolResult, ToolSpec


def _ctx(**kwargs):
    invocation = AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1,
        phase="independent_analysis", agent_id="agent-ms-1", role="master_student", task="inspect",
    ).model_copy(update=kwargs)
    return build_tool_execution_context(invocation, runtime_name="pi", limits=kwargs.get("limits"))


def test_duplicate_request_is_not_executed_twice_and_is_audited() -> None:
    calls = []
    registry = ToolRegistry()
    spec = ToolSpec(name="memory.query", version="1.0", description="read", read_only=True,
                    allowed_roles=["master_student"], allowed_phases=["independent_analysis"], data_spaces=["synthetic"])
    registry.register(spec, lambda request, context: (calls.append(1) or ToolResult(
        request_id=request.request_id, name=request.name, version="1.0", payload={"items": []}
    )))
    request = ToolRequest(request_id="same", name="memory.query")
    registry.execute(request, _ctx())
    duplicate = registry.execute(request, _ctx())
    assert duplicate.status == "limit_exceeded" and duplicate.error_code == "duplicate_request"
    assert calls == [1]
    assert [record.status for record in registry.audit("run-1")] == ["success", "limit_exceeded"]


def test_result_size_limit_and_unauthorized_requests_are_rejected() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(name="memory.query", version="1.0", description="read", read_only=True,
                    allowed_roles=["master_student"], allowed_phases=["independent_analysis"], data_spaces=["synthetic"])
    registry.register(spec, lambda request, context: ToolResult(
        request_id=request.request_id, name=request.name, version="1.0", payload={"data": "x" * 100}
    ))
    limited = registry.execute(
        ToolRequest(request_id="large", name="memory.query"),
        _ctx(limits=ToolLimits(max_result_bytes=10)),
    )
    assert limited.status == "limit_exceeded"
    forbidden = registry.execute(
        ToolRequest(request_id="phd", name="memory.query"), _ctx(role="phd_student")
    )
    assert forbidden.status == "denied"
    assert registry.audit("run-1")[-1].authorization == "denied"


def test_secret_like_arguments_never_appear_in_audit() -> None:
    registry = build_synthetic_registry()
    registry.execute(ToolRequest(
        request_id="secret", name="literature.search",
        arguments={"query": "LLM_API_KEY=secret-value"},
    ), _ctx())
    record = registry.audit("run-1")[0]
    serialized = record.model_dump_json()
    assert "secret-value" not in serialized
    assert "LLM_API_KEY" not in serialized
