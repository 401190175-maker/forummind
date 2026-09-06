from app.tools import ToolRegistry, build_synthetic_registry
from app.tools.audit import AuditRecorder


def test_default_registry_contains_only_three_synthetic_read_only_tools() -> None:
    registry = build_synthetic_registry()
    assert [spec.name for spec in registry.list_specs.__self__._specs.values()] == [
        "memory.query", "literature.search", "experiment.analyze_demo"
    ]
    assert all(spec.read_only and spec.data_spaces == ["synthetic"] for spec in registry._specs.values())


def test_default_registry_accepts_independent_audit_recorder() -> None:
    first = AuditRecorder()
    left = build_synthetic_registry(first)
    right = build_synthetic_registry()
    assert isinstance(left, ToolRegistry) and left._audit is first
    assert left._audit is not right._audit
