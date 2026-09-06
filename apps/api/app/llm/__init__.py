"""LLM Provider 模块：OpenAI-compatible LLM 调用原语（live 半场底座）。"""

from app.llm.provider import LLMConfig, LLMError, chat, load_config

__all__ = ["LLMConfig", "LLMError", "chat", "load_config"]
