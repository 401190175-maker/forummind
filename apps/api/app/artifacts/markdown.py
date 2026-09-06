"""Markdown artifact rendering for independent master research outputs."""

from __future__ import annotations

import re
from datetime import datetime


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", value.strip())
    return normalized[:80] or "Agent"


def master_artifact_filename(*, timestamp: float, task_name: str, agent_name: str) -> str:
    date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    return f"{date}_{_safe_filename(task_name)}_{_safe_filename(agent_name)}.md"


def build_master_markdown(
    *,
    agent_name: str,
    agent_id: str,
    topic_name: str,
    initial_intent: str,
    content: str,
    fields: dict[str, str],
    runtime: str,
    profile_version: str,
    instruction_version: str,
    data_space: str,
) -> str:
    """Render a self-contained, traceable Markdown research artifact."""
    lines = [
        f"# {agent_name} 独立研究记录",
        "",
        f"- Agent ID: `{agent_id}`",
        f"- 课题: {topic_name}",
        f"- 任务意图: {initial_intent or '未指定'}",
        f"- Runtime: `{runtime}`",
        f"- Profile 版本: `{profile_version}`",
        f"- Instruction 版本: `{instruction_version}`",
        f"- 数据空间: `{data_space}`",
        "",
        "## 独立判断",
        "",
        content.strip(),
        "",
        "## 结构化观点",
        "",
        f"### 判断\n{fields.get('statement', '')}",
        f"\n### 适用边界\n{fields.get('boundary', '')}",
        f"\n### 可观察预测\n{fields.get('prediction', '')}",
        f"\n### 可推翻条件\n{fields.get('falsification_condition', '')}",
        "",
        "> 本文件是 Agent 独立分析的候选研究产物，须经过博士组会前质量审查和 PI 决策。",
    ]
    return "\n".join(lines).strip() + "\n"
