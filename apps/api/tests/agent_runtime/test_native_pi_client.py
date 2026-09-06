import asyncio

import app.agent_runtime.native_pi_client as native_pi_client
import pytest
from app.agent_runtime.native_pi_client import NativePiClient
from app.agent_runtime.pi_client import PiProtocolError
from app.agent_runtime.schemas import AgentInvocation


class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = [
            Response(200, {"session_id": "sess-1", "cursor": 0, "persisted": False}),
            Response(200, {"accepted": True, "cursor": 0}),
            Response(200, {"events": [{
                "event_id": "evt-1", "cursor": 1, "session_id": "sess-1", "invocation_id": "inv-1",
                "run_id": "run-1", "group_chat_id": "gc-1", "agent_id": "agent-ms-1",
                "phase": "independent_analysis", "type": "agent_settled",
                "payload": {"result": {"content": "x", "structured_output": {}}},
                "data_space": "synthetic", "timestamp": 1.0,
            }]})
        ]

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def invocation():
    return AgentInvocation(
        run_id="run-1", group_chat_id="gc-1", cycle=1, phase="independent_analysis",
        agent_id="agent-ms-1", role="master_student", task="task", data_space="synthetic",
    )


def test_native_pi_client_maps_settled_event_to_agent_result():
    http = FakeClient()
    client = NativePiClient("http://pi-runtime", "token", client=http)
    result = asyncio.run(client.invoke(invocation().model_dump()))
    assert result["agent_id"] == "agent-ms-1"
    assert result["status"] == "ok"
    assert http.calls[0][2]["headers"] == {"X-ForumMind-Runtime-Token": "token"}


def test_native_pi_client_retains_events_and_updates_session_cursor():
    class EventClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.responses = [
                Response(200, {"session_id": "sess-1", "cursor": 0, "persisted": True}),
                Response(200, {"accepted": True, "cursor": 0}),
                Response(200, {"events": [
                    {
                        "event_id": "evt-1", "cursor": 1, "session_id": "sess-1",
                        "invocation_id": "inv-1", "run_id": "run-1", "group_chat_id": "gc-1",
                        "agent_id": "agent-ms-1", "phase": "independent_analysis",
                        "type": "text_delta", "payload": {"content_delta": "candidate"},
                        "data_space": "synthetic", "timestamp": 1.0,
                    },
                    {
                        "event_id": "evt-2", "cursor": 2, "session_id": "sess-1",
                        "invocation_id": "inv-1", "run_id": "run-1", "group_chat_id": "gc-1",
                        "agent_id": "agent-ms-1", "phase": "independent_analysis",
                        "type": "agent_settled",
                        "payload": {"result": {"content": "x", "structured_output": {}}},
                        "data_space": "synthetic", "timestamp": 2.0,
                    },
                ]})
            ]

    client = NativePiClient("http://pi-runtime", "token", client=EventClient())
    request = invocation().model_copy(update={"invocation_id": "inv-1"})
    asyncio.run(client.invoke(request.model_dump()))

    assert [item["event_id"] for item in client.last_events["inv-1"]] == ["evt-1", "evt-2"]
    assert client.last_sessions["agent-ms-1"].cursor == 2


def test_native_pi_client_preserves_agent_failure_error_code():
    class FailedEventClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.responses = [
                Response(200, {"session_id": "sess-1", "cursor": 0, "persisted": True}),
                Response(200, {"accepted": True, "cursor": 0}),
                Response(200, {"events": [{
                    "event_id": "evt-failed", "cursor": 1, "session_id": "sess-1",
                    "invocation_id": "inv-1", "run_id": "run-1", "group_chat_id": "gc-1",
                    "agent_id": "agent-ms-1", "phase": "independent_analysis",
                    "type": "agent_failed",
                    "payload": {"error": "401: invalid_api_key", "error_code": "pi_auth"},
                    "data_space": "synthetic", "timestamp": 1.0,
                }]}),
            ]

    client = NativePiClient("http://pi-runtime", "token", client=FailedEventClient())
    request = invocation().model_copy(update={"invocation_id": "inv-1"})

    result = asyncio.run(client.invoke(request.model_dump()))

    assert result["status"] == "error"
    assert result["error"] == "401: invalid_api_key"
    assert result["error_code"] == "pi_auth"


def test_native_pi_client_reads_events_from_before_completed_prompt_cursor():
    class CompletedPromptClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.responses = [
                Response(200, {"session_id": "sess-1", "cursor": 0, "persisted": True}),
                Response(200, {"accepted": True, "cursor": 2}),
            ]

        async def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if method == "GET" and url.endswith("/events?after=0"):
                return Response(200, {"events": [{
                    "event_id": "evt-settled", "cursor": 3, "session_id": "sess-1",
                    "invocation_id": "inv-1", "run_id": "run-1", "group_chat_id": "gc-1",
                    "agent_id": "agent-ms-1", "phase": "independent_analysis",
                    "type": "agent_settled",
                    "payload": {"result": {"content": "x", "structured_output": {}}},
                    "data_space": "synthetic", "timestamp": 3.0,
                }]})
            if method == "GET" and "/events?after=" in url:
                raise AssertionError("client skipped settled events using the completed prompt cursor")
            return self.responses.pop(0)

    client = NativePiClient(
        "http://pi-runtime", "token", client=CompletedPromptClient(), poll_interval=0
    )
    result = asyncio.run(client.invoke(invocation().model_copy(update={"invocation_id": "inv-1"}).model_dump()))

    assert result["status"] == "ok"


def test_native_pi_client_preserves_runtime_rejection_reason():
    class RejectedPromptClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.responses = [
                Response(200, {"session_id": "sess-1", "cursor": 0, "persisted": True}),
                Response(200, {
                    "accepted": False,
                    "cursor": 4,
                    "error": "result exceeds configured byte limit",
                    "error_code": "result_too_large",
                }),
            ]

    client = NativePiClient("http://pi-runtime", "token", client=RejectedPromptClient())

    with pytest.raises(PiProtocolError, match="result exceeds configured byte limit"):
        asyncio.run(client.invoke(invocation().model_copy(update={"invocation_id": "inv-1"}).model_dump()))


def test_native_pi_client_exposes_control_methods():
    class ControlClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.responses = [Response(200, {"accepted": True}), Response(200, {"disposed": True})]

    http = ControlClient()
    client = NativePiClient("http://pi-runtime", "token", client=http)
    assert asyncio.run(client.steer("s", "pause"))["accepted"] is True
    assert asyncio.run(client.abort("s"))["disposed"] is True


def test_native_pi_client_does_not_route_local_sidecar_through_environment_proxy(monkeypatch):
    captured = {}

    class LocalClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def request(self, method, url, **kwargs):
            return Response(200, {"configured": True})

        async def aclose(self):
            return None

    monkeypatch.setattr(native_pi_client.httpx, "AsyncClient", LocalClient)

    result = asyncio.run(NativePiClient("http://127.0.0.1:8010", "token").health())

    assert result["configured"] is True
    assert captured["trust_env"] is False


def test_native_pi_client_uses_separate_timeout_for_long_running_prompts():
    class PromptClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.responses = [Response(200, {"accepted": True, "cursor": 0})]

    http = PromptClient()
    client = NativePiClient(
        "http://pi-runtime",
        "token",
        timeout=5,
        prompt_timeout=15,
        client=http,
    )

    result = asyncio.run(client.prompt("sess-1", invocation()))

    assert result["accepted"] is True
    assert http.calls[0][2]["timeout"] == 15
