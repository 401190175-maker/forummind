"""Role-aware invocation policy tests."""

from app.agent_runtime.instruction_builder import RoleInvocationBuilder


def _scope(role: str, phase: str) -> dict:
    return {
        "agent_id": f"agent-{role}",
        "name": role,
        "role": role,
        "phase": phase,
        "data_space": "synthetic",
        "allowed_tools": [
            "memory.query",
            "literature.search",
            "experiment.analyze_demo",
            "knowledge.search",
        ],
        "task": "比较孔结构与抗压强度的候选机制",
    }


def test_role_builder_assigns_distinct_phase_contracts_and_tool_scopes() -> None:
    master = RoleInvocationBuilder.build(
        "master_student", "independent_analysis", _scope("master_student", "independent_analysis")
    )
    reviewer = RoleInvocationBuilder.build(
        "phd_student", "review_gate", _scope("phd_student", "review_gate")
    )
    postdoc = RoleInvocationBuilder.build(
        "postdoc", "postdoc_exchange", _scope("postdoc", "postdoc_exchange")
    )

    assert master.output_contract == "claim_four_fields"
    assert master.allowed_tools == [
        "memory.query",
        "literature.search",
        "experiment.analyze_demo",
    ]
    assert reviewer.output_contract == "review_gate"
    assert reviewer.allowed_tools == []
    assert postdoc.output_contract == "postdoc_synthesis"
    assert postdoc.allowed_tools == []
    assert reviewer.allowed_tools != master.allowed_tools
    assert "PI 决策" in reviewer.task
    assert "专业范围" in postdoc.task


def test_role_builder_rejects_unsupported_role_phase_pair() -> None:
    try:
        RoleInvocationBuilder.build(
            "phd_student", "independent_analysis", _scope("phd_student", "independent_analysis")
        )
    except ValueError as exc:
        assert "role/phase" in str(exc)
    else:
        raise AssertionError("unsupported role/phase pair must be rejected")


def test_master_builder_uses_policy_default_tools_when_scope_omits_tools() -> None:
    scope = _scope("master_student", "independent_analysis")
    scope.pop("allowed_tools")

    plan = RoleInvocationBuilder.build(
        "master_student", "independent_analysis", scope
    )

    assert plan.allowed_tools == [
        "memory.query",
        "literature.search",
        "experiment.analyze_demo",
    ]
