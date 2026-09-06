"""Agent Runtime DTO 测试（tasks.md Task 18）。"""
import pytest
from pydantic import ValidationError

from app.agent_runtime import (
    AgentInvocation,
    AgentResult,
    CandidateStreamEvent,
    RuntimeSelection,
)
from app.agent_runtime.schemas import (
    AgentInvocation as Invocation,
    AgentResult as Result,
    CandidateStreamEvent as StreamEvent,
    RuntimeSelection as Selection,
)


# ---------------- AgentInvocation ----------------

def test_invocation_defaults() -> None:
    invocation = Invocation(agent_id="agent-ms-1", role="master_student", task="分析")
    assert invocation.run_id == ""
    assert invocation.group_chat_id == ""
    assert invocation.cycle is None
    assert invocation.phase == ""
    assert invocation.input_refs == []
    assert invocation.context == {}
    assert invocation.allowed_tools == []
    assert invocation.output_contract == "free_text"
    assert invocation.data_space == "synthetic"
    assert invocation.safety_rules == []


def test_invocation_full() -> None:
    invocation = Invocation(
        run_id="run-1",
        group_chat_id="gc-1",
        cycle=2,
        phase="independent_analysis",
        agent_id="agent-phd-1",
        role="phd_student",
        task="审查观点",
        input_refs=["claim-1"],
        context={"cycle": 1},
        allowed_tools=["query_memory"],
        output_contract="review_gate",
        safety_rules=["no_formal_memory_write"],
    )
    assert invocation.run_id == "run-1"
    assert invocation.group_chat_id == "gc-1"
    assert invocation.cycle == 2
    assert invocation.phase == "independent_analysis"
    assert invocation.input_refs == ["claim-1"]
    assert invocation.context == {"cycle": 1}
    assert invocation.allowed_tools == ["query_memory"]
    assert invocation.safety_rules == ["no_formal_memory_write"]


def test_invocation_list_defaults_are_isolated() -> None:
    first = Invocation(agent_id="agent-ms-1", role="master_student", task="分析")
    second = Invocation(agent_id="agent-ms-2", role="master_student", task="分析")
    first.input_refs.append("claim-1")
    first.allowed_tools.append("query_memory")
    first.safety_rules.append("no_formal_memory_write")
    assert second.input_refs == []
    assert second.allowed_tools == []
    assert second.safety_rules == []


def test_invocation_requires_agent_and_task() -> None:
    """agent_id / role / task 为必填字段（design §4.5 为普通 str，无非空约束）。"""
    with pytest.raises(ValidationError):
        Invocation(agent_id="a", role="x")  # 缺 task
    with pytest.raises(ValidationError):
        Invocation(agent_id="a", task="t")  # 缺 role
    with pytest.raises(ValidationError):
        Invocation(role="x", task="t")  # 缺 agent_id


# ---------------- AgentResult ----------------

def test_result_status_ok() -> None:
    result = Result(status="ok", content="判断文本")
    assert result.agent_id == ""
    assert result.structured_output == {}
    assert result.tool_calls == []
    assert result.runtime_state_ref == ""
    assert result.warnings == []
    assert result.error == ""
    assert result.data_space == "synthetic"


def test_result_statuses() -> None:
    assert Result(status="fallback", content="剧本回退").status == "fallback"
    assert Result(status="error", content="").status == "error"


@pytest.mark.parametrize("bad_status", ["success", "failed", "", "OK"])
def test_result_rejects_invalid_status(bad_status: str) -> None:
    with pytest.raises(ValidationError):
        Result(status=bad_status, content="x")  # type: ignore[arg-type]


def test_result_structured_output_and_warnings() -> None:
    result = Result(
        agent_id="agent-ms-1",
        status="ok",
        content="c",
        structured_output={"key": 1},
        tool_calls=[{"name": "query_memory"}],
        runtime_state_ref="state-1",
        warnings=["w1"],
        error="",
        data_space="synthetic",
    )
    assert result.agent_id == "agent-ms-1"
    assert result.structured_output == {"key": 1}
    assert result.tool_calls == [{"name": "query_memory"}]
    assert result.runtime_state_ref == "state-1"
    assert result.warnings == ["w1"]


def test_result_tool_calls_default_is_isolated() -> None:
    first = Result(status="ok", content="a")
    second = Result(status="ok", content="b")
    first.tool_calls.append({"name": "query_memory"})
    assert second.tool_calls == []


# ---------------- RuntimeSelection ----------------

def test_runtime_selection_defaults() -> None:
    selection = Selection(api_mode="auto", resolved_mode="replay")
    assert selection.api_mode == "auto"
    assert selection.resolved_mode == "replay"
    assert selection.runtime_name == ""
    assert selection.fallback_reason == ""
    assert selection.warnings == []


def test_runtime_selection_live_runtime() -> None:
    selection = Selection(
        api_mode="live",
        resolved_mode="live",
        runtime_name="legacy_llm",
        warnings=["explicit live mode"],
    )
    assert selection.runtime_name == "legacy_llm"
    assert selection.warnings == ["explicit live mode"]


@pytest.mark.parametrize("api_mode", ["batch", "debug", ""])
def test_runtime_selection_rejects_invalid_api_mode(api_mode: str) -> None:
    with pytest.raises(ValidationError):
        Selection(api_mode=api_mode, resolved_mode="live")  # type: ignore[arg-type]


@pytest.mark.parametrize("resolved_mode", ["auto", "debug", ""])
def test_runtime_selection_rejects_invalid_resolved_mode(resolved_mode: str) -> None:
    with pytest.raises(ValidationError):
        Selection(api_mode="auto", resolved_mode=resolved_mode)  # type: ignore[arg-type]


@pytest.mark.parametrize("runtime_name", ["legacy_llm", "mock", "pi", "unavailable", ""])
def test_runtime_selection_allows_supported_runtime_names(runtime_name: str) -> None:
    selection = Selection(
        api_mode="auto",
        resolved_mode="live" if runtime_name else "replay",
        runtime_name=runtime_name,
    )
    assert selection.runtime_name == runtime_name


def test_runtime_selection_rejects_unknown_runtime_name() -> None:
    with pytest.raises(ValidationError):
        Selection(
            api_mode="auto",
            resolved_mode="live",
            runtime_name="unknown",
        )


def test_runtime_selection_warning_defaults_are_isolated() -> None:
    first = Selection(api_mode="auto", resolved_mode="replay")
    second = Selection(api_mode="auto", resolved_mode="replay")
    first.warnings.append("no key")
    assert second.warnings == []


# ---------------- CandidateStreamEvent ----------------

def test_stream_event_minimal() -> None:
    event = StreamEvent(
        id="evt-1", run_id="run-1", agent_id="agent-ms-1",
        content_delta="文本", status="streaming",
    )
    assert event.data_space == "synthetic"


def test_stream_event_statuses() -> None:
    for status in ("streaming", "completed", "validated", "rejected"):
        event = StreamEvent(
            id="e", run_id="r", agent_id="a", content_delta="", status=status
        )
        assert event.status == status


@pytest.mark.parametrize("bad_status", ["pending", "approved", ""])
def test_stream_event_rejects_invalid_status(bad_status: str) -> None:
    with pytest.raises(ValidationError):
        StreamEvent(
            id="e", run_id="r", agent_id="a", content_delta="", status=bad_status
        )  # type: ignore[arg-type]


# ---------------- 导出与边界 ----------------

def test_package_exports_dtos() -> None:
    assert AgentInvocation is Invocation
    assert AgentResult is Result
    assert CandidateStreamEvent is StreamEvent
    assert RuntimeSelection is Selection


def test_schemas_do_not_import_fastapi_or_llm() -> None:
    """DTO 不导入 FastAPI，不访问 LLM（导入面检查）。"""
    import inspect

    source = inspect.getsource(Invocation)
    module_source = inspect.getsource(__import__("app.agent_runtime.schemas", fromlist=["*"]))
    for forbidden in ("fastapi", "app.llm", "httpx", "open("):
        assert forbidden not in module_source, forbidden
    assert "pydantic" in module_source
    assert source  # 非空
