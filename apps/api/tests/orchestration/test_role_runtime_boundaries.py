from app.agent_runtime.result_validation import validate_role_output
from app.agent_runtime.schemas import AgentInvocation, AgentResult


def _invocation(**overrides: object) -> AgentInvocation:
    values: dict[str, object] = {
        "run_id": "run-1",
        "group_chat_id": "group-1",
        "cycle": 1,
        "phase": "review_gate",
        "agent_id": "agent-phd-1",
        "role": "phd_student",
        "profile_version": "v1",
        "task": "审查候选观点",
        "output_contract": "review_gate",
        "data_space": "synthetic",
    }
    values.update(overrides)
    return AgentInvocation(**values)


def _result(invocation: AgentInvocation, **overrides: object) -> AgentResult:
    values: dict[str, object] = {
        "agent_id": invocation.agent_id,
        "status": "ok",
        "content": "审查意见",
        "structured_output": {
            "items": [
                {"kind": "counterexample", "content": "反例"},
                {"kind": "falsification_condition", "content": "可推翻条件"},
                {"kind": "missing_observation", "content": "缺失观察"},
            ]
        },
        "data_space": invocation.data_space,
    }
    values.update(overrides)
    return AgentResult(**values)


def test_phd_review_cannot_return_pi_decision() -> None:
    result = validate_role_output(
        _invocation(),
        _result(_invocation(), structured_output={"option": "approved"}),
    )

    assert result.valid is False
    assert "review_gate" in result.reason


def test_postdoc_out_of_domain_response_is_refused() -> None:
    invocation = _invocation(
        phase="postdoc_exchange",
        role="postdoc",
        agent_id="agent-postdoc-1",
        task="量子编程建议",
        output_contract="postdoc_exchange",
        context={"specialty_domain": "泡沫混凝土"},
    )
    result = validate_role_output(
        invocation,
        AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="量子编程建议",
            data_space=invocation.data_space,
        ),
    )

    assert result.valid is False
    assert result.code == "domain_guard"


def test_postdoc_prompt_domain_does_not_authorize_an_out_of_domain_response() -> None:
    invocation = _invocation(
        phase="postdoc_exchange",
        role="postdoc",
        agent_id="agent-postdoc-1",
        task="请在泡沫混凝土范围内完成综合",
        output_contract="postdoc_synthesis",
        context={"specialty_domain": "泡沫混凝土"},
    )
    result = validate_role_output(
        invocation,
        AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="量子编程建议",
            structured_output={"summary": "量子编程建议"},
            data_space=invocation.data_space,
        ),
    )

    assert result.valid is False
    assert result.code == "domain_guard"


def test_master_independent_output_keeps_claim_contract() -> None:
    invocation = _invocation(
        phase="independent_analysis",
        role="master_student",
        agent_id="agent-ms-1",
        task="形成候选观点",
        output_contract="claim_four_fields",
    )
    result = validate_role_output(
        invocation,
        AgentResult(
            agent_id=invocation.agent_id,
            status="ok",
            content="候选",
            structured_output={"statement": "只有一个字段"},
            data_space=invocation.data_space,
        ),
    )

    assert result.valid is False
    assert "claim_four_fields" in result.reason
