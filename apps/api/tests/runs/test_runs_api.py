"""Run API 单元 + 集成测试。"""
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agent_runtime.schemas import RuntimeSelection

client = TestClient(app)


def _group_chat_payload() -> dict:
    return {
        "topic_name": "废弃泥浆基泡沫混凝土",
        "topic_summary": "研究废弃泥浆基泡沫混凝土的机理与性能",
        "member_selection": {
            "postdoc": {
                "selection_mode": "existing",
                "agent_ids": ["agent-postdoc-1"],
            },
            "phd_student": {
                "selection_mode": "existing",
                "agent_ids": ["agent-phd-1"],
            },
            "master_student": {"selection_mode": "generate", "count": 3},
        },
    }


def _create_group_chat_id() -> str:
    response = client.post("/group-chats", json=_group_chat_payload())
    assert response.status_code == 200
    return response.json()["group_chat"]["id"]


def _existing_group_chat_payload() -> dict:
    payload = _group_chat_payload()
    payload["member_selection"]["master_student"] = {
        "selection_mode": "existing",
        "agent_ids": ["agent-ms-1", "agent-ms-2", "agent-ms-3"],
    }
    return payload


def _create_existing_group_chat_id() -> str:
    response = client.post("/group-chats", json=_existing_group_chat_payload())
    assert response.status_code == 200
    return response.json()["group_chat"]["id"]


def _start_replay() -> str:
    group_chat_id = _create_group_chat_id()
    response = client.post(f"/group-chats/{group_chat_id}/runs", json={"mode": "replay"})
    assert response.status_code == 200
    return response.json()["run_id"]


def test_resolve_mode_auto_without_pi_is_live(monkeypatch):
    from app.api import runs

    def fake_policy(api_mode: str) -> RuntimeSelection:
        assert api_mode == "auto"
        return RuntimeSelection(
            api_mode="auto", resolved_mode="live", runtime_name="unavailable"
        )

    monkeypatch.setattr(runs, "resolve_runtime_policy", fake_policy)
    assert runs._resolve_mode("auto") == "live"


def test_resolve_mode_auto_with_key_is_live(monkeypatch):
    from app.api import runs

    def fake_policy(api_mode: str) -> RuntimeSelection:
        assert api_mode == "auto"
        return RuntimeSelection(
            api_mode="auto",
            resolved_mode="live",
            runtime_name="pi",
        )

    monkeypatch.setattr(runs, "resolve_runtime_policy", fake_policy)
    assert runs._resolve_mode("auto") == "live"


def test_resolve_mode_replay_uses_runtime_policy(monkeypatch):
    from app.api import runs

    calls: list[str] = []

    def fake_policy(api_mode: str) -> RuntimeSelection:
        calls.append(api_mode)
        return RuntimeSelection(api_mode="replay", resolved_mode="replay")

    monkeypatch.setattr(runs, "resolve_runtime_policy", fake_policy)
    assert runs._resolve_mode("replay") == "replay"
    assert calls == ["replay"]


def test_snapshot_has_all_fields():
    from app.api import runs

    state = runs.run_store.create("gc-1", "replay")
    snap = runs._snapshot(state)
    assert set(snap) == {
        "run_id", "status", "mode", "phase", "cycle", "agent_specs",
        "review_agent_spec", "runtime_name", "task_context", "artifacts",
        "error", "steps", "memory", "memory_views", "experiment_view",
        "tool_calls",
    }
    assert snap["tool_calls"] == []


def test_start_replay_reaches_meeting():
    group_chat_id = _create_group_chat_id()
    r = client.post(f"/group-chats/{group_chat_id}/runs", json={"mode": "replay"})
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"].startswith("run-")
    assert body["status"] == "awaiting_decision"


def test_start_run_requires_created_group_chat():
    r = client.post("/group-chats/not-created/runs", json={"mode": "replay"})
    assert r.status_code == 404


def test_start_auto_without_pi_fails_explicitly(monkeypatch):
    from app.api import runs

    monkeypatch.setattr(
        runs,
        "resolve_runtime_policy",
        lambda api_mode: RuntimeSelection(
            api_mode=api_mode,
            resolved_mode="live",
            runtime_name="unavailable",
            fallback_reason="Pi runtime is unavailable: PI_ENABLED is not enabled",
        ),
    )
    group_chat_id = _create_group_chat_id()
    r = client.post(f"/group-chats/{group_chat_id}/runs", json={"mode": "auto"})
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


def test_start_live_returns_run_id():
    group_chat_id = _create_group_chat_id()
    r = client.post(f"/group-chats/{group_chat_id}/runs", json={"mode": "live"})
    assert r.status_code == 200
    assert r.json()["run_id"].startswith("run-")


def test_live_run_freezes_existing_enabled_master_agents(monkeypatch):
    from app.api import runs

    group_chat_id = _create_existing_group_chat_id()
    captured = {}
    completed = threading.Event()

    async def fake_run_live(scenario, state, **kwargs):
        captured["state"] = state
        completed.set()

    monkeypatch.setattr(runs, "run_live", fake_run_live)
    monkeypatch.setattr(
        runs,
        "resolve_runtime_policy",
        lambda api_mode, **kwargs: RuntimeSelection(
            api_mode=api_mode, resolved_mode="live", runtime_name="pi"
        ),
    )

    response = client.post(
        f"/group-chats/{group_chat_id}/runs", json={"mode": "live"}
    )

    assert response.status_code == 200
    assert completed.wait(2)
    state = captured["state"]
    assert [spec["agent_id"] for spec in state.agent_specs] == [
        "agent-ms-1",
        "agent-ms-2",
        "agent-ms-3",
    ]
    assert state.runtime_name == "pi"


def test_live_member_resolution_ignores_pending_generation_members(monkeypatch):
    from app.api import runs

    def record(agent_id: str) -> dict:
        return {
            "agent_id": agent_id,
            "enabled": True,
            "profile": {
                "agent_id": agent_id,
                "name": agent_id,
                "role": "master_student",
                "primary_ability": "机制",
            },
        }

    monkeypatch.setattr(runs.agents_service, "get_agent_record", record)
    group_chat = SimpleNamespace(
        members=[
            SimpleNamespace(
                role="master_student",
                selection_mode="existing",
                status="active",
                agent_profile_ref=SimpleNamespace(object_id="agent-ms-1"),
            ),
            SimpleNamespace(
                role="master_student",
                selection_mode="generate",
                status="pending_generation",
                agent_profile_ref=None,
            ),
            SimpleNamespace(
                role="master_student",
                selection_mode="existing",
                status="active",
                agent_profile_ref=SimpleNamespace(object_id="agent-ms-2"),
            ),
        ]
    )

    with pytest.raises(ValueError, match="至少需要三个"):
        runs._resolve_live_agent_specs(group_chat)


def test_live_member_resolution_excludes_agents_without_group_data_access(monkeypatch):
    from app.api import runs

    def record(agent_id: str) -> dict:
        allowed_space = (
            "desensitized_real" if agent_id == "agent-real" else "synthetic"
        )
        return {
            "agent_id": agent_id,
            "enabled": True,
            "profile": {
                "agent_id": agent_id,
                "name": agent_id,
                "role": "master_student",
                "primary_ability": "机制分析",
                "allowed_data_spaces": [allowed_space],
            },
        }

    monkeypatch.setattr(runs.agents_service, "get_agent_record", record)
    group_chat = SimpleNamespace(
        group_chat=SimpleNamespace(data_space="desensitized_real"),
        members=[
            SimpleNamespace(
                role="master_student",
                selection_mode="existing",
                status="active",
                agent_profile_ref=SimpleNamespace(object_id=f"agent:{agent_id}"),
            )
            for agent_id in ["agent-real", "agent-demo-b", "agent-demo-c"]
        ],
    )

    with pytest.raises(ValueError, match="至少需要三个"):
        runs._resolve_live_agent_specs(
            group_chat, required_data_space="desensitized_real"
        )


def test_live_run_with_unavailable_pi_is_failed_without_replay(monkeypatch):
    from app.api import runs

    group_chat_id = _create_existing_group_chat_id()
    monkeypatch.setattr(
        runs,
        "resolve_runtime_policy",
        lambda api_mode, **kwargs: RuntimeSelection(
            api_mode=api_mode,
            resolved_mode="live",
            runtime_name="unavailable",
            fallback_reason="Pi runtime is unavailable: PI_ENABLED is not enabled",
        ),
    )

    response = client.post(
        f"/group-chats/{group_chat_id}/runs", json={"mode": "auto"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    snapshot = client.get(f"/runs/{response.json()['run_id']}").json()
    assert snapshot["mode"] == "live"
    assert snapshot["status"] == "failed"
    assert "PI_ENABLED" in snapshot["error"]
    assert not any(
        step["kind"] == "claim" and step["payload"].get("source") == "scenario"
        for step in snapshot["steps"]
    )


def test_get_run_snapshot_fields():
    run_id = _start_replay()
    snap = client.get(f"/runs/{run_id}").json()
    assert set(snap) == {
        "run_id", "status", "mode", "phase", "cycle", "agent_specs",
        "review_agent_spec", "runtime_name", "task_context", "artifacts",
        "error", "steps", "memory", "memory_views", "experiment_view",
        "tool_calls",
    }
    assert snap["tool_calls"] == []
    assert snap["phase"] == "meeting"


def test_meeting_events_route_reads_replay_run_with_scenario_sources():
    run_id = _start_replay()
    response = client.get(f"/runs/{run_id}/meeting-events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 7
    assert [event["kind"] for event in events[:3]] == ["master_report"] * 3
    assert all(event["source"] == "scenario" for event in events)
    assert all(
        any(ref.startswith("artifact:") for ref in event["source_refs"])
        for event in events[:3]
    )


def test_meeting_message_route_persists_pi_interruption():
    run_id = _start_replay()
    response = client.post(
        f"/runs/{run_id}/meeting-messages",
        json={"content": "请补充判别实验的控制条件"},
    )
    assert response.status_code == 200
    event = response.json()
    assert event["actor_id"] == "PI"
    assert event["kind"] == "message"
    events = client.get(f"/runs/{run_id}/meeting-events").json()
    assert events[-1] == event
    assert len(events) == 8


def test_meeting_message_route_rejects_blank_content():
    run_id = _start_replay()
    response = client.post(f"/runs/{run_id}/meeting-messages", json={"content": "  "})
    assert response.status_code == 422


def test_formal_meeting_routes_require_persistence(monkeypatch):
    from app.api import runs

    run_id = _start_replay()
    monkeypatch.setattr(runs, "_meeting_service", None)

    events_response = client.get(f"/runs/{run_id}/meeting-events")
    decision_response = client.post(
        f"/runs/{run_id}/decision",
        json={"option": "approved", "reason": "r"},
    )

    assert events_response.status_code == 503
    assert decision_response.status_code == 503


def test_snapshot_memory_views_shape():
    run_id = _start_replay()
    snap = client.get(f"/runs/{run_id}").json()
    views = snap["memory_views"]
    assert set(views) == {"timeline", "version_tree", "evidence_graph"}
    assert isinstance(views["timeline"], list)
    assert isinstance(views["version_tree"], list)
    assert set(views["evidence_graph"]) == {"nodes", "edges"}
    # raw memory 保留且与 timeline 投影条数一致（同一批 entries）
    assert len(snap["memory"]) == len(views["timeline"])


def test_run_snapshot_experiment_view_empty_plan_and_results_before_approval():
    run_id = _start_replay()
    snap = client.get(f"/runs/{run_id}").json()

    view = snap["experiment_view"]
    assert set(view) == {
        "data_space",
        "phase",
        "plan",
        "results",
        "hypothesis_updates",
        "research_state_change",
        "boundary_notes",
    }
    assert view["data_space"] == "synthetic"
    assert view["phase"] == "meeting"
    assert view["plan"] is None
    assert view["results"] is None


def test_run_snapshot_experiment_view_after_approval_contains_plan_memory():
    run_id = _start_replay()
    snap = client.post(
        f"/runs/{run_id}/decision",
        json={"option": "approved_with_conditions", "reason": "按条件批准"},
    ).json()

    view = snap["experiment_view"]
    plan_memories = [m for m in snap["memory"] if m["kind"] == "ExperimentPlan"]
    assert snap["phase"] == "discriminating_experiment"
    assert len(plan_memories) == 1
    assert view["plan"]["candidate_explanations"]
    assert view["plan"]["approval_boundary"] == {
        "option": "approved_with_conditions",
        "reason": "按条件批准",
    }
    assert view["results"] is None


def test_run_snapshot_experiment_view_after_import_contains_results_updates_and_state_change():
    run_id = _start_replay()
    client.post(f"/runs/{run_id}/decision", json={"option": "approved", "reason": "r"})

    snap = client.post(f"/runs/{run_id}/experiment-results").json()

    view = snap["experiment_view"]
    assert snap["phase"] == "conclusion"
    assert view["results"]["source"] == "demo_csv"
    assert view["results"]["validation_summary"]
    assert len(view["hypothesis_updates"]) == 3
    assert view["research_state_change"]["supersedes"] is True
    assert view["research_state_change"]["preserves_old_version"] is True


def test_decision_returned_advances_cycle():
    run_id = _start_replay()
    snap = client.post(f"/runs/{run_id}/decision",
                       json={"option": "returned", "reason": "证据不足"}).json()
    assert snap["cycle"] == 2
    assert any(s["kind"] == "decision" and s["payload"].get("next_meeting") == "第 2 周组会"
               for s in snap["steps"])


def test_decision_invalid_option_422():
    run_id = _start_replay()
    r = client.post(f"/runs/{run_id}/decision", json={"option": "maybe", "reason": "r"})
    assert r.status_code == 422


def test_decision_rejects_after_terminal_state():
    run_id = _start_replay()
    client.post(f"/runs/{run_id}/decision", json={"option": "terminated", "reason": "stop"})
    r = client.post(f"/runs/{run_id}/decision", json={"option": "approved", "reason": "late"})
    assert r.status_code == 422


def test_import_requires_approved_experiment_phase():
    run_id = _start_replay()
    r = client.post(f"/runs/{run_id}/experiment-results")
    assert r.status_code == 422


def test_import_rejects_duplicate_results():
    run_id = _start_replay()
    client.post(f"/runs/{run_id}/decision", json={"option": "approved", "reason": "r"})
    first = client.post(f"/runs/{run_id}/experiment-results")
    assert first.status_code == 200
    second = client.post(f"/runs/{run_id}/experiment-results")
    assert second.status_code == 422


def test_import_reaches_conclusion():
    run_id = _start_replay()
    client.post(f"/runs/{run_id}/decision", json={"option": "approved", "reason": "r"})
    snap = client.post(f"/runs/{run_id}/experiment-results").json()
    assert snap["phase"] == "conclusion"


def test_get_missing_run_404():
    assert client.get("/runs/nope").status_code == 404


def test_agents_three_masters_distinct():
    r = client.get("/agents")
    assert r.status_code == 200
    body = r.json()
    assert body["data_space"] == "synthetic"
    masters = [a for a in body["agents"] if a["role"] == "master_student"]
    assert len(masters) == 3
    assert len({a["primary_ability"] for a in masters}) == 3
