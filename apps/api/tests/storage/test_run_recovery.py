"""Durable Run metadata recovery tests."""

from app.orchestration.run_store import RunStep, RunStore
from app.storage.sqlite_store import SQLiteStore


def test_run_store_recovers_live_agent_metadata_and_failure(tmp_path):
    path = tmp_path / "forummind.db"
    first_db = SQLiteStore(path)
    first_db.initialize()
    specs = [
        {"agent_id": f"agent-live-{index}", "role": "master_student"}
        for index in range(1, 4)
    ]
    original = RunStore(first_db).create(
        "gc-1", "live", agent_specs=specs, runtime_name="pi"
    )
    original.status = "failed"
    original.phase = "failed"
    original.error = "agent-live-2 returned an error"
    original.steps.append(
        RunStep(
            "step-failed",
            "independent_analysis",
            "invocation",
            "agent-live-2",
            "runtime error",
            {"status": "error", "agent_id": "agent-live-2"},
            1.0,
        )
    )
    original.persist()
    first_db.close()

    second_db = SQLiteStore(path)
    second_db.initialize()
    recovered = RunStore(second_db).get(original.run_id)

    assert recovered is not None
    assert recovered.agent_specs == specs
    assert recovered.runtime_name == "pi"
    assert recovered.status == "failed"
    assert recovered.phase == "failed"
    assert recovered.error == "agent-live-2 returned an error"
    assert recovered.steps[-1].actor == "agent-live-2"
    second_db.close()
