"""OpenAI-compatible transport regression tests."""

import asyncio

from app.agent_runtime.pi_http_client import HttpPiClient


class FakeResponse:
    status_code = 200
    text = "ok"

    def json(self):
        return {
            "choices": [
                {"message": {"content": '{"question":"请明确证据边界","question_id":"q-1"}'}},
            ]
        }


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, *, headers, json, timeout):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()


def test_openai_compatible_client_posts_chat_completion_and_normalizes_json():
    http_client = FakeHttpClient()
    client = HttpPiClient(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="secret-key",
        protocol="openai_compatible",
        client=http_client,
    )

    result = asyncio.run(
        client.invoke(
            {
                "model": "qwen-plus",
                "task": "请提出下一条澄清问题",
                "agent_instruction": {
                    "agent_id": "agent-phd-1",
                    "role": "phd_student",
                    "identity": "博士 Agent",
                },
                "context": {"initial_intent": "解释强度变化", "turns": []},
            }
        )
    )

    call = http_client.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer secret-key"
    assert call["json"]["model"] == "qwen-plus"
    assert call["json"]["messages"][0]["role"] == "system"
    assert "agent-phd-1" in call["json"]["messages"][0]["content"]
    assert call["json"]["messages"][1]["role"] == "user"
    assert "解释强度变化" in call["json"]["messages"][1]["content"]
    assert result["content"] == '{"question":"请明确证据边界","question_id":"q-1"}'
    assert result["structured_output"] == {
        "question": "请明确证据边界",
        "question_id": "q-1",
    }

