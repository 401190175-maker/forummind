"""LLM Provider 单元测试：全 mock，不访问真实网络。"""
import asyncio

import httpx
import pytest

from app.llm.provider import LLMConfig, LLMError, chat, load_config


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class FakeClient:
    """假 httpx.AsyncClient：记录请求并返回预设响应。"""

    def __init__(self, response):
        self.response = response
        self.captured = {}

    async def post(self, url, **kwargs):
        self.captured["url"] = url
        self.captured["headers"] = kwargs["headers"]
        self.captured["json"] = kwargs["json"]
        return self.response


def _config(api_key="k"):
    return LLMConfig(base_url="http://x/v1", api_key=api_key, model="m")


def test_chat_returns_content(monkeypatch):
    monkeypatch.setattr("app.llm.provider.load_config", lambda: _config())
    client = FakeClient(FakeResponse(200, {"choices": [{"message": {"content": "OK"}}]}))
    result = asyncio.run(chat([{"role": "user", "content": "hi"}], client=client))
    assert result == "OK"
    assert client.captured["url"] == "http://x/v1/chat/completions"
    assert client.captured["headers"]["Authorization"] == "Bearer k"
    assert client.captured["json"]["model"] == "m"


def test_chat_raises_without_key(monkeypatch):
    monkeypatch.setattr("app.llm.provider.load_config", lambda: _config(api_key=""))
    with pytest.raises(LLMError):
        asyncio.run(chat([{"role": "user", "content": "hi"}]))


def test_chat_raises_on_http_error(monkeypatch):
    monkeypatch.setattr("app.llm.provider.load_config", lambda: _config())
    client = FakeClient(FakeResponse(401, text="unauthorized"))
    with pytest.raises(LLMError):
        asyncio.run(chat([{"role": "user", "content": "hi"}], client=client))


def test_chat_raises_on_malformed_response(monkeypatch):
    monkeypatch.setattr("app.llm.provider.load_config", lambda: _config())
    client = FakeClient(FakeResponse(200, {}))
    with pytest.raises(LLMError):
        asyncio.run(chat([{"role": "user", "content": "hi"}], client=client))


def test_chat_wraps_httpx_error(monkeypatch):
    monkeypatch.setattr("app.llm.provider.load_config", lambda: _config())

    class BoomClient:
        async def post(self, url, **kwargs):
            raise httpx.ConnectError("network down")

    with pytest.raises(LLMError) as excinfo:
        asyncio.run(chat([{"role": "user", "content": "hi"}], client=BoomClient()))
    assert "network down" in str(excinfo.value)
