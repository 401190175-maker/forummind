"""Scenario 加载器：按 package_id 返回确定性剧本。"""
from __future__ import annotations

from app.scenario.schema import Scenario


class ScenarioNotFound(KeyError):
    pass


_REGISTRY: dict[str, Scenario] = {}


def _register() -> None:
    from app.scenario.foam_concrete import FOAM_CONCRETE_SCENARIO
    _REGISTRY[FOAM_CONCRETE_SCENARIO.package_id] = FOAM_CONCRETE_SCENARIO


def load_scenario(package_id: str) -> Scenario:
    if not _REGISTRY:
        _register()
    if package_id not in _REGISTRY:
        raise ScenarioNotFound(f"未知剧本包：{package_id}")
    return _REGISTRY[package_id]
