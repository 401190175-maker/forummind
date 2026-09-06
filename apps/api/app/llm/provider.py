"""OpenAI-compatible LLM provider（DashScope/Qwen）。"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str


def load_config() -> LLMConfig:
    """从环境变量读取 LLM 配置；key 只来自环境，不写死。"""
    return LLMConfig(
        base_url=os.getenv(
            "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "qwen-plus"),
    )


class LLMError(RuntimeError):
    """LLM 调用失败（未配置/网络/鉴权/响应结构异常）。"""


async def chat(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    client: httpx.AsyncClient | None = None,
) -> str:
    """调用 OpenAI-compatible chat completions，返回 assistant 文本。

    失败（未配置 key、网络、HTTP 非 200、响应结构异常）统一抛 LLMError。
    """
    config = load_config()
    if not config.api_key:
        raise LLMError("LLM_API_KEY 未配置")
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60)
    try:
        resp = await client.post(
            f"{config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json=payload,
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM 网络错误: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()
    if resp.status_code != 200:
        raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM 响应结构异常") from exc
