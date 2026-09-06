"""`app.demo_data.package_schema` Demo 数据包 schema 测试。

全部用例在内存中构造数据包字典，不访问文件系统、不读取真实数据包文件。
"""

import importlib

import pytest
from pydantic import ValidationError

from app.demo_data.package_schema import DemoDataPackage


def build_minimal_package() -> dict[str, object]:
    """构造一份最小合法数据包（内存字典，键与接口契约一一对应）。"""
    return {
        "package_id": "foam_concrete_case",
        "version": "0.1.0",
        "label": "废弃泥浆基泡沫混凝土合成 Demo 数据包",
        "synthetic_notice": (
            "本数据包仅用于演示流程（demo-only）。所有内容为合成材料（synthetic），"
            "不是科研证据（non-evidence），不代表真实实验、真实文献或真实人员。"
        ),
        "research_direction": {
            "title": "废弃泥浆基泡沫混凝土机理-性能-制备全链条研究（合成演示）",
            "description": "围绕废弃泥浆基泡沫混凝土的机理、性能与制备开展全链条研究（演示用合成方向，非真实课题）",
            "material_system": "废弃泥浆基泡沫混凝土",
            "phenomenon_or_objective": "解释废弃泥浆掺量对泡沫混凝土孔结构与抗压强度的影响规律",
            "to_explain": ["泥浆掺量提高后抗压强度下降的候选机理"],
        },
        "literature_leads": [
            {
                "local_key": "lit-1",
                "title": "泥浆固相含量对泡沫混凝土孔结构影响的合成文献线索",
                "summary": "合成线索：固相含量升高可能降低泡沫稳定性（待核查）",
                "status": "lead",
                "note": "合成文献线索，仅作待核查材料，不是已核查证据",
            }
        ],
        "experiment_constraints": {
            "equipment": "小型搅拌机、发泡机、万能试验机、显微镜（演示约束，非真实设备清单）",
            "timeline": "4 周（演示周期约束）",
            "samples": "演示用样品编号 S-DEMO-01 起（合成编号，不代表真实样品）",
            "cost": "演示预算（合成数字）",
            "measurable_indicators": ["28d 抗压强度（演示数值）", "孔结构观测（演示描述）"],
            "safety_boundary": "演示环境仅使用无害合成材料描述，不涉及真实危化品操作",
        },
        "initial_anomaly": {
            "local_key": "anomaly-1",
            "title": "泥浆掺量提高后抗压强度下降（合成异常描述）",
            "description": "合成异常描述：泥浆掺量从 10% 提高到 30% 时抗压强度出现下降趋势，大孔比例增加。此为合成异常描述，不是真实实验结论。",
            "is_synthetic_anomaly": True,
            "not_experiment_result_note": "本异常仅为演示而构造的合成异常描述，不代表任何真实实验结论",
        },
        "agent_profiles": [
            {
                "local_key": "agent-ms-1",
                "name": "演示硕士生 Agent",
                "role": "master_student",
                "primary_ability": "梳理文献线索并整理演示材料",
                "allowed_data_spaces": ["synthetic"],
            }
        ],
        "initial_tasks": [
            {
                "local_key": "task-1",
                "title": "整理合成文献线索清单",
                "description": "把数据包内合成文献线索整理为待核查材料清单（演示任务）",
                "assigner": "agent-ms-1",
                "assignee": "agent-ms-1",
                "expected_output_object_type": "evidence",
                "input_local_keys": ["lit-1"],
                "status": "pending",
            }
        ],
        "expected_initial_state": {
            "summary": "演示初始状态：合成课题已建立，文献线索待核查，初始异常为合成异常描述",
            "key_evidence_local_keys": ["lit-1", "anomaly-1"],
            "evidence_gaps_summary": "所有证据均为合成材料，无真实实验证据（演示状态）",
            "unresolved_disagreements_summary": "暂无未决分歧（演示初始状态）",
        },
        "reset_policy": {
            "scope": "仅重建内存中的确定性演示对象集合；不删除文件、不写数据库、不修改全局状态",
            "determinism": "同一数据包版本多次 reset 产生同一对象集合、对象引用与序列化结果",
            "allowed_spaces": ["synthetic"],
        },
        "integrity_rules": [
            "所有内容为合成材料（synthetic），仅用于演示（demo-only），不是科研证据（non-evidence）"
        ],
    }


def test_module_is_importable() -> None:
    """`app.demo_data.package_schema` 可被导入。"""
    module = importlib.import_module("app.demo_data.package_schema")
    assert module.__name__ == "app.demo_data.package_schema"


def test_demo_data_package_importable() -> None:
    """`DemoDataPackage` 可从 `app.demo_data.package_schema` 导入。"""
    assert DemoDataPackage.__name__ == "DemoDataPackage"


def test_minimal_package_validates() -> None:
    """最小合法数据包（内存构造，镜像契约形状）通过校验，关键值按契约保留。"""
    package = DemoDataPackage.model_validate(build_minimal_package())
    assert package.package_id == "foam_concrete_case"
    assert package.version == "0.1.0"
    assert package.synthetic_notice.startswith("本数据包仅用于演示流程")
    assert package.research_direction.material_system == "废弃泥浆基泡沫混凝土"
    assert package.literature_leads[0].status == "lead"
    assert package.initial_anomaly.is_synthetic_anomaly is True
    assert package.agent_profiles[0].allowed_data_spaces == ["synthetic"]
    assert package.initial_tasks[0].expected_output_object_type == "evidence"
    assert package.initial_tasks[0].status == "pending"
    assert package.reset_policy.allowed_spaces == ["synthetic"]


def test_missing_synthetic_notice_raises() -> None:
    """缺少合成声明（synthetic_notice）时校验失败。"""
    data = build_minimal_package()
    del data["synthetic_notice"]
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize(
    "field", ["research_direction", "experiment_constraints", "initial_anomaly"]
)
def test_missing_core_section_raises(field: str) -> None:
    """缺少研究方向、实验约束或初始异常时校验失败。"""
    data = build_minimal_package()
    del data[field]
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize("status", ["verified", "rejected", "confirmed"])
def test_literature_lead_invalid_status_raises(status: str) -> None:
    """文献线索状态只能是 lead/pending，verified 等已核查类值校验失败。"""
    data = build_minimal_package()
    data["literature_leads"][0]["status"] = status
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize("status", ["lead", "pending"])
def test_literature_lead_valid_status_accepted(status: str) -> None:
    """文献线索状态 lead 与 pending 均被接受。"""
    data = build_minimal_package()
    data["literature_leads"][0]["status"] = status
    package = DemoDataPackage.model_validate(data)
    assert package.literature_leads[0].status == status


def test_initial_anomaly_missing_synthetic_marker_raises() -> None:
    """初始异常缺少 is_synthetic_anomaly 标记字段时校验失败。"""
    data = build_minimal_package()
    del data["initial_anomaly"]["is_synthetic_anomaly"]
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


def test_unknown_top_level_key_rejected() -> None:
    """未知顶层键被拒绝（extra=forbid），保持契约紧凑。"""
    data = build_minimal_package()
    data["unexpected_key"] = "unexpected"
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_blank_synthetic_notice_raises(value: str) -> None:
    """合成声明不允许为空或纯空白。"""
    data = build_minimal_package()
    data["synthetic_notice"] = value
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_package_id_raises(value: str) -> None:
    """数据包标识不允许为空或纯空白。"""
    data = build_minimal_package()
    data["package_id"] = value
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


def test_agent_profile_without_synthetic_space_raises() -> None:
    """Agent 允许数据空间不包含 synthetic 时校验失败。"""
    data = build_minimal_package()
    data["agent_profiles"][0]["allowed_data_spaces"] = ["real"]
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


def test_agent_profile_with_synthetic_space_passes() -> None:
    """Agent 允许数据空间包含 synthetic（可附带其他空间，非 exclusive）时通过校验。"""
    data = build_minimal_package()
    data["agent_profiles"][0]["allowed_data_spaces"] = ["synthetic", "real"]
    package = DemoDataPackage.model_validate(data)
    assert package.agent_profiles[0].allowed_data_spaces == ["synthetic", "real"]


def test_reset_policy_without_synthetic_space_raises() -> None:
    """Reset 策略允许数据空间不包含 synthetic 时校验失败。"""
    data = build_minimal_package()
    data["reset_policy"]["allowed_spaces"] = ["real"]
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize(
    "role", ["master_student", "phd_student", "postdoc", "group_meeting_secretary"]
)
def test_agent_role_valid_values_accepted(role: str) -> None:
    """四种 AgentRole 值均被接受。"""
    data = build_minimal_package()
    data["agent_profiles"][0]["role"] = role
    package = DemoDataPackage.model_validate(data)
    assert package.agent_profiles[0].role == role


@pytest.mark.parametrize("role", ["professor", "undergraduate", "admin"])
def test_agent_role_invalid_value_raises(role: str) -> None:
    """Agent 角色使用未定义值时校验失败。"""
    data = build_minimal_package()
    data["agent_profiles"][0]["role"] = role
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize(
    "object_type",
    [
        "project",
        "research_question",
        "agent_profile",
        "task",
        "claim",
        "evidence",
        "research_state",
    ],
)
def test_expected_output_object_type_valid_values_accepted(object_type: str) -> None:
    """七种 ObjectType 值均被接受。"""
    data = build_minimal_package()
    data["initial_tasks"][0]["expected_output_object_type"] = object_type
    package = DemoDataPackage.model_validate(data)
    assert package.initial_tasks[0].expected_output_object_type == object_type


@pytest.mark.parametrize("object_type", ["note", "experiment", "publication"])
def test_expected_output_object_type_invalid_value_raises(object_type: str) -> None:
    """任务预期输出对象类型使用未定义值时校验失败。"""
    data = build_minimal_package()
    data["initial_tasks"][0]["expected_output_object_type"] = object_type
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


@pytest.mark.parametrize(
    "status", ["pending", "in_progress", "blocked", "completed", "cancelled"]
)
def test_task_status_valid_values_accepted(status: str) -> None:
    """五种 TaskStatus 值均被接受。"""
    data = build_minimal_package()
    data["initial_tasks"][0]["status"] = status
    package = DemoDataPackage.model_validate(data)
    assert package.initial_tasks[0].status == status


@pytest.mark.parametrize("status", ["done", "failed", "suspended"])
def test_task_status_invalid_value_raises(status: str) -> None:
    """任务状态使用未定义值时校验失败。"""
    data = build_minimal_package()
    data["initial_tasks"][0]["status"] = status
    with pytest.raises(ValidationError):
        DemoDataPackage.model_validate(data)


def test_package_field_surface_mirrors_contract() -> None:
    """DemoDataPackage 顶层字段与接口契约键一一对应。"""
    assert set(DemoDataPackage.model_fields) == {
        "package_id",
        "version",
        "label",
        "synthetic_notice",
        "research_direction",
        "literature_leads",
        "experiment_constraints",
        "initial_anomaly",
        "agent_profiles",
        "initial_tasks",
        "expected_initial_state",
        "reset_policy",
        "integrity_rules",
    }
