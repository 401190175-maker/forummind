"""Run engine and API persistence integration tests."""

from app.api import runs as runs_api
from app.orchestration.engine import run_import, run_replay
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario
from app.storage.repositories import ArtifactRepository, MeetingRepository
from app.storage.sqlite_store import SQLiteStore


def test_replay_persists_after_workflow_and_recovers(tmp_path):
    path = tmp_path / "forummind.db"
    first = SQLiteStore(path)
    first.initialize()
    first_store = RunStore(first)
    state = first_store.create("gc-1", "replay")

    run_replay(load_scenario("foam_concrete_case"), state)
    stored_step_ids = [step.id for step in state.steps]
    first.close()

    reopened = SQLiteStore(path)
    reopened.initialize()
    recovered = RunStore(reopened).get(state.run_id)

    assert recovered is not None
    assert recovered.status == "awaiting_decision"
    assert recovered.phase == "meeting"
    assert [step.id for step in recovered.steps] == stored_step_ids
    reopened.close()


def test_recovered_run_can_append_steps_without_reusing_ids(tmp_path):
    path = tmp_path / "forummind.db"
    first = SQLiteStore(path)
    first.initialize()
    state = RunStore(first).create("gc-1", "replay")
    scenario = load_scenario("foam_concrete_case")
    run_replay(scenario, state)
    original_ids = {step.id for step in state.steps}
    first.close()

    reopened = SQLiteStore(path)
    reopened.initialize()
    recovered = RunStore(reopened).get(state.run_id)
    run_replay(scenario, recovered)

    assert len(recovered.steps) == len({step.id for step in recovered.steps})
    assert original_ids.isdisjoint({step.id for step in recovered.steps[len(original_ids):]})
    reopened.close()


def test_decision_appends_a_meeting_event(tmp_path):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    runs_api.run_store.configure_persistence(database)
    runs_api.configure_persistence(database)
    state = runs_api.run_store.create("gc-1", "replay")
    run_replay(load_scenario("foam_concrete_case"), state)

    try:
        snapshot = runs_api.decide(
            state.run_id,
            runs_api.DecisionRequest(option="approved", reason="保留最小判别实验"),
        )

        events = MeetingRepository(database).list_events(state.run_id)
        artifacts = ArtifactRepository(database).list_for_run(state.run_id)
        assert snapshot["status"] == "completed"
        assert len(artifacts) == 3
        assert {artifact["agent_id"] for artifact in artifacts} == {
            "agent-ms-1",
            "agent-ms-2",
            "agent-ms-3",
        }
        assert len(events) == 8
        assert [event["kind"] for event in events] == [
            "master_report",
            "master_report",
            "master_report",
            "postdoc_request",
            "postdoc_response",
            "postdoc_request",
            "postdoc_response",
            "decision",
        ]
        assert [event["source"] for event in events[:7]] == ["scenario"] * 7
        assert events[-1]["source"] == "pi"
        artifact_ids = {artifact["artifact_id"] for artifact in artifacts}
        assert all(
            any(ref in artifact_ids for ref in event["source_refs"])
            for event in events[:3]
        )
        assert events[-1]["source_refs"]
        assert events[-1]["source_refs"][0].startswith("step-")
    finally:
        runs_api.run_store.reset()
        runs_api.configure_persistence(None)
        database.close()


def test_import_persists_conclusion_state(tmp_path):
    database = SQLiteStore(tmp_path / "forummind.db")
    database.initialize()
    store = RunStore(database)
    state = store.create("gc-1", "replay")
    scenario = load_scenario("foam_concrete_case")
    run_replay(scenario, state)
    from app.orchestration.engine import apply_decision

    apply_decision(scenario, state, "approved", "允许导入 demo 结果")
    run_import(scenario, state)
    database.close()

    reopened = SQLiteStore(tmp_path / "forummind.db")
    reopened.initialize()
    recovered = RunStore(reopened).get(state.run_id)
    assert recovered is not None
    assert recovered.phase == "conclusion"
    assert recovered.status == "conclusion"
    reopened.close()
