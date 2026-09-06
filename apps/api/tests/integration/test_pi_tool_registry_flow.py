import asyncio
import itertools

import pytest

from app.agent_runtime.pi_runtime import PiRuntime
from app.api import runs
from app.orchestration import engine
from app.orchestration.run_store import RunStore
from app.scenario.loader import load_scenario
import app.memory.timeline as memory_timeline


@pytest.fixture(autouse=True)
def isolate_memory_sequence():
    """The legacy in-process demo counter must not leak across test packages."""
    memory_timeline._seq = itertools.count(1)
    yield
    memory_timeline._seq = itertools.count(1)


class SequencePi:
    def __init__(self):
        self.requests = []
        self._step = 0

    async def invoke(self, request):
        self.requests.append(request)
        self._step += 1
        action = (self._step - 1) % 4
        if action < 3:
            names = ["memory.query", "literature.search", "experiment.analyze_demo"]
            return {"type": "tool_request", "request_id": f"req-{self._step}", "name": names[action], "arguments": {}}
        return {"type": "final", "agent_id": request["agent_id"], "content": "candidate", "structured_output": {
            "statement": "candidate", "boundary": "b", "prediction": "p", "falsification_condition": "f"
        }}


def test_fake_pi_three_tools_flow_reaches_orchestration_and_snapshot(monkeypatch):
    client = SequencePi()
    captured = {}

    def make_runtime(**kwargs):
        captured.update(kwargs)
        kwargs.pop("runtime_name", None)
        return PiRuntime(client, **kwargs)

    monkeypatch.setattr(engine, "create_runtime", make_runtime)
    state = RunStore().create(
        "gc-1",
        "live",
        runtime_name="pi",
        agent_specs=[
            {
                "agent_id": f"agent-live-{index}",
                "role": "master_student",
                "primary_ability": "独立科研分析",
            }
            for index in range(1, 4)
        ],
    )
    asyncio.run(engine.run_live(load_scenario("foam_concrete_case"), state))
    records = state.tool_audit_records
    assert len(records) == 9
    assert {record.tool_name for record in records} == {
        "memory.query", "literature.search", "experiment.analyze_demo"
    }
    assert all(record.status == "success" and record.authorization == "allowed" for record in records)
    assert all(record.phase == "independent_analysis" and record.data_space == "synthetic" for record in records)
    snapshot = runs._snapshot(state)
    assert len(snapshot["tool_calls"]) == 9
    assert len(snapshot["memory"]) > 0
    assert captured["tool_registry"] is not None
