"""Process-local Agent Runtime configuration.

Secrets are intentionally kept out of Pydantic response models and SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

from pydantic import BaseModel


class RuntimeConfigStatus(BaseModel):
    configured: bool
    provider: str = ""
    base_url: str = ""
    model: str = ""
    updated_at: float | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    provider: str
    base_url: str
    model: str
    api_key: str
    updated_at: float


class RuntimeConfigStore:
    """Hold one local Runtime configuration for the running API process.

    The API key stays in this process-local object. Status responses and
    persisted Run data use RuntimeConfigStatus, which has no secret field.
    """

    def __init__(self) -> None:
        self._config: RuntimeConfig | None = None

    def configure(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str,
    ) -> RuntimeConfigStatus:
        provider = provider.strip()
        base_url = base_url.strip()
        model = model.strip()
        api_key = api_key.strip()
        if not provider:
            raise ValueError("provider must be non-empty")
        if not model:
            raise ValueError("model must be non-empty")
        if not base_url and not api_key:
            raise ValueError("base_url or api_key must be configured")
        if not api_key and self._config is not None:
            api_key = self._config.api_key
        self._config = RuntimeConfig(
            provider=provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
            updated_at=time.time(),
        )
        return self.status()

    def clear(self) -> RuntimeConfigStatus:
        """Drop the in-memory provider configuration, including its secret."""
        self._config = None
        return self.status()

    def current(self) -> RuntimeConfig | None:
        return self._config

    def status(self) -> RuntimeConfigStatus:
        if self._config is None:
            return RuntimeConfigStatus(configured=False)
        return RuntimeConfigStatus(
            configured=True,
            provider=self._config.provider,
            base_url=self._config.base_url,
            model=self._config.model,
            updated_at=self._config.updated_at,
        )


runtime_config = RuntimeConfigStore()
