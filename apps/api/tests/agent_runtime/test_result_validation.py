"""Agent Runtime result validation tests (Task 5)."""

import inspect

import pytest

from app.agent_runtime.result_validation import (
    ValidationResult,
    validate_agent_result,
)
from app.agent_runtime.schemas import AgentInvocation, AgentResult


def _invocation(*, output_contract: str = "claim_four_fields") -> AgentInvocation:
    return AgentInvocation(
        agent_id="agent-ms-1",
        role="master_student",
        task="分析泡沫混凝土的孔结构机制",
        output_contract=output_contract,
        data_space="synthetic",
    )


def _valid_result(**overrides: object) -> AgentResult:
    values: dict[str, object] = {
        "agent_id": "agent-ms-1",
        "status": "ok",
        "content": "孔结构影响强度和吸水率。",
        "structured_output": {
            "statement": "孔结构是强度变化的主要机制。",
            "boundary": "低密度且浆体均匀的样品",
            "prediction": "大孔比例升高时抗压强度下降",
            "falsification_condition": "控制孔结构后强度差异消失",
        },
        "data_space": "synthetic",
    }
    values.update(overrides)
    return AgentResult(**values)


def test_valid_claim_result_passes() -> None:
    result = validate_agent_result(_invocation(), _valid_result())

    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.reason == ""


def test_real_research_claim_contract_requires_evidence_fields() -> None:
    invocation = AgentInvocation(
        agent_id="agent-ms-1",
        role="master_student",
        phase="independent_analysis",
        output_contract="research_claim",
        task="完成真实任务候选分析",
        data_space="desensitized_real",
        task_id="task-1",
        document_scope=["doc-1"],
    )
    result = AgentResult(
        agent_id="agent-ms-1",
        status="ok",
        content="候选结论",
        structured_output={
            "claim": "资料支持该趋势",
            "evidence_refs": ["chunk-1"],
            "reasoning_summary": "依据授权资料",
            "uncertainty": "样本有限",
        },
        data_space="desensitized_real",
    )

    validation = validate_agent_result(invocation, result)

    assert not validation.valid
    assert "next_action" in validation.reason


def test_phd_review_accepts_provider_category_arrays() -> None:
    invocation = AgentInvocation(
        agent_id="agent-phd-1",
        role="phd_student",
        phase="review_gate",
        output_contract="review_gate",
        task="执行候选审查",
        data_space="desensitized_real",
        task_id="task-1",
        document_scope=["doc-1"],
    )
    result = AgentResult(
        agent_id="agent-phd-1",
        status="ok",
        content="审查意见",
        structured_output={
            "counterexample": ["反例"],
            "falsification_condition": ["可推翻条件"],
            "missing_observation": ["缺失观察"],
        },
        data_space="desensitized_real",
    )

    validation = validate_agent_result(invocation, result)

    assert validation.valid is True


def test_phd_review_accepts_provider_category_objects_with_descriptions() -> None:
    invocation = AgentInvocation(
        agent_id="agent-phd-1",
        role="phd_student",
        phase="review_gate",
        output_contract="review_gate",
        task="执行候选审查",
        data_space="desensitized_real",
        task_id="task-1",
        document_scope=["doc-1"],
    )
    result = AgentResult(
        agent_id="agent-phd-1",
        status="ok",
        content="审查意见",
        structured_output={
            "counterexample": [{"type": "counterexample", "description": "反例"}],
            "falsification_condition": [{"type": "falsification_condition", "description": "可推翻条件"}],
            "missing_observation": [{"type": "missing_observation", "description": "缺失观察"}],
        },
        data_space="desensitized_real",
    )

    validation = validate_agent_result(invocation, result)

    assert validation.valid is True


def test_phd_review_accepts_provider_category_objects_with_statements() -> None:
    invocation = AgentInvocation(
        agent_id="agent-phd-1",
        role="phd_student",
        phase="review_gate",
        output_contract="review_gate",
        task="执行候选审查",
        data_space="desensitized_real",
        task_id="task-1",
        document_scope=["doc-1"],
    )
    result = AgentResult(
        agent_id="agent-phd-1",
        status="ok",
        content="审查意见",
        structured_output={
            "counterexample": [{"type": "counterexample", "statement": "反例"}],
            "falsification_condition": [{"type": "falsification_condition", "statement": "可推翻条件"}],
            "missing_observation": [{"type": "missing_observation", "statement": "缺失观察"}],
        },
        data_space="desensitized_real",
    )

    validation = validate_agent_result(invocation, result)

    assert validation.valid is True


def test_phd_review_accepts_nested_review_result_items() -> None:
    invocation = AgentInvocation(
        agent_id="agent-phd-1",
        role="phd_student",
        phase="review_gate",
        output_contract="review_gate",
        task="执行候选审查",
        data_space="desensitized_real",
        task_id="task-1",
        document_scope=["doc-1"],
    )
    result = AgentResult(
        agent_id="agent-phd-1",
        status="ok",
        content="审查意见",
        structured_output={
            "review_result": {
                "review_basis": "只读审查",
                "review_items": [
                    {"candidate_id": "candidate-1", "type": "counterexample", "finding": "反例", "requested_revision": "补充边界"},
                    {"candidate_id": "candidate-1", "type": "falsification_condition", "finding": "可推翻条件", "requested_revision": "补充判据"},
                    {"candidate_id": "candidate-1", "type": "missing_observation", "finding": "缺失观察", "requested_revision": "补充测量"},
                ],
                "gate_recommendation_candidate": "建议 PI 审阅",
            },
        },
        data_space="desensitized_real",
    )

    validation = validate_agent_result(invocation, result)

    assert validation.valid is True


def test_phd_review_accepts_category_objects_wrapping_items() -> None:
    invocation = AgentInvocation(
        agent_id="agent-phd-1",
        role="phd_student",
        phase="review_gate",
        output_contract="review_gate",
        task="执行候选审查",
        data_space="desensitized_real",
        task_id="task-1",
        document_scope=["doc-1"],
    )
    result = AgentResult(
        agent_id="agent-phd-1",
        status="ok",
        content="审查意见",
        structured_output={
            "counterexample": {
                "items": [{"agent_id": "agent-ms-1", "finding": "反例"}],
                "candidate_gate_recommendation": "保留候选状态",
            },
            "falsification_condition": {
                "items": [{"agent_id": "agent-ms-1", "finding": "可推翻条件"}],
                "candidate_gate_recommendation": "补充判据",
            },
            "missing_observation": {
                "items": [{"agent_id": "agent-ms-1", "finding": "缺失观察"}],
                "candidate_gate_recommendation": "补充测量",
            },
        },
        data_space="desensitized_real",
    )

    validation = validate_agent_result(invocation, result)

    assert validation.valid is True


def test_non_claim_contract_only_requires_common_result_fields() -> None:
    result = validate_agent_result(
        _invocation(output_contract="free_text"),
        _valid_result(structured_output={}),
    )

    assert result.valid is True


@pytest.mark.parametrize(
    ("overrides", "reason_fragment"),
    [
        ({"status": "error", "content": ""}, "status"),
        ({"agent_id": "agent-ms-2"}, "agent_id"),
        ({"data_space": "real"}, "data_space"),
        ({"content": "   "}, "content"),
    ],
)
def test_common_result_contract_failures_are_readable(
    overrides: dict[str, object], reason_fragment: str
) -> None:
    result = validate_agent_result(_invocation(), _valid_result(**overrides))

    assert result.valid is False
    assert reason_fragment in result.reason


@pytest.mark.parametrize(
    "missing_field",
    ["statement", "boundary", "prediction", "falsification_condition"],
)
def test_claim_result_requires_all_four_structured_fields(missing_field: str) -> None:
    structured_output = _valid_result().structured_output
    del structured_output[missing_field]

    result = validate_agent_result(
        _invocation(), _valid_result(structured_output=structured_output)
    )

    assert result.valid is False
    assert missing_field in result.reason


def test_claim_result_rejects_blank_structured_fields() -> None:
    result = validate_agent_result(
        _invocation(),
        _valid_result(
            structured_output={
                "statement": "判断",
                "boundary": "边界",
                "prediction": "预测",
                "falsification_condition": "   ",
            }
        ),
    )

    assert result.valid is False
    assert "falsification_condition" in result.reason


def test_validation_module_has_no_business_or_transport_dependencies() -> None:
    module = __import__(
        "app.agent_runtime.result_validation", fromlist=["validate_agent_result"]
    )
    source = inspect.getsource(module).lower()
    for forbidden in ("fastapi", "memory", "runstore", "pi_client", "httpx"):
        assert forbidden not in source, forbidden
