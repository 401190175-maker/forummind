import type { AgentInvocation } from "./contracts.js";

export function buildForumMindSystemPrompt(invocation: AgentInvocation): string {
  return renderForumMindSystemPrompt({
    agent_id: invocation.agent_id,
    role: invocation.role,
    phase: invocation.phase,
    profile_version: invocation.profile_version,
    allowed_tools: invocation.allowed_tools,
    data_space: invocation.data_space,
    output_contract: invocation.output_contract,
    safety_rules: invocation.safety_rules,
    frozen_instruction: invocation.agent_instruction,
  });
}

export function renderForumMindSystemPrompt(instruction: {
  agent_id: string;
  role: string;
  phase: string;
  profile_version?: string;
  responsibilities?: string[];
  phase_rules?: string[];
  allowed_tools?: string[];
  forbidden_actions?: string[];
  data_space?: string;
  output_contract?: string;
  safety_rules?: string[];
  frozen_instruction?: string;
}): string {
  return [
    "ForumMind Agent",
    "你是 ForumMind 科研执行 Agent，不是通用 coding assistant。",
    "ForumMind 控制阶段、审查门、正式 Memory、产物和 PI 决策；当前 Session 只能返回候选结果。",
    JSON.stringify(instruction, null, 2),
    "所有输出均为候选内容；不得直接写入正式 Memory、改变阶段或作 PI 决策。",
  ].join("\n\n");
}
