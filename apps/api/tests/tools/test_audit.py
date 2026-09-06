from app.tools.audit import AuditRecorder
from app.tools.schemas import ToolCallRecord


def _record(run_id: str, request_id: str) -> ToolCallRecord:
    return ToolCallRecord(
        record_id=f"audit-{request_id}", request_id=request_id, run_id=run_id,
        group_chat_id="gc-1", cycle=1, phase="independent_analysis",
        agent_id="agent-ms-1", role="master_student", runtime="pi",
        tool_name="memory.query", tool_version="1.0", authorization="allowed",
        status="success", argument_summary={"keys": ["kind"]}, source_refs=[],
        result_summary={"items": 1}, requested_data_space="synthetic",
        returned_data_space="synthetic", policy_version="p2-v1", started_at=1,
        duration_ms=1,
    )


def test_audit_is_append_only_isolated_and_returns_copies() -> None:
    seen = []
    recorder = AuditRecorder(sink=seen.append)
    recorder.append(_record("run-1", "r-1"))
    recorder.append(_record("run-2", "r-2"))
    records = recorder.list_for_run("run-1")
    records[0].result_summary["items"] = 99
    assert [item.request_id for item in recorder.list_for_run("run-1")] == ["r-1"]
    assert recorder.list_for_run("run-1")[0].result_summary["items"] == 1
    assert [item.request_id for item in seen] == ["r-1", "r-2"]


def test_audit_reset_scopes_to_run() -> None:
    recorder = AuditRecorder()
    recorder.append(_record("run-1", "r-1"))
    recorder.append(_record("run-2", "r-2"))
    recorder.reset("run-1")
    assert recorder.list_for_run("run-1") == []
    assert [item.request_id for item in recorder.list_for_run("run-2")] == ["r-2"]
    recorder.reset()
    assert recorder.list_for_run("run-2") == []
