import assert from "node:assert/strict";
import { test } from "node:test";

import type { AgentInvocation } from "../src/contracts.js";
import { renderForumMindSystemPrompt } from "../src/system-prompt.js";
import { validateInvocationRoleBoundary } from "../src/session-registry.js";

function invocation(overrides: Partial<AgentInvocation> = {}): AgentInvocation {
  return {
    invocation_id: "inv-1",
    run_id: "run-1",
    group_chat_id: "group-1",
    cycle: 1,
    phase: "review_gate",
    agent_id: "agent-phd-1",
    role: "phd_student",
    profile_version: "v1",
    agent_instruction: "ForumMind AgentInstruction",
    task: "审查候选观点",
    input_refs: [],
    context: {},
    allowed_tools: [],
    output_contract: "review_gate",
    data_space: "synthetic",
    safety_rules: ["no_formal_memory_write"],
    ...overrides,
  };
}

test("native sessions reject role and phase mismatches", () => {
  assert.throws(
    () => validateInvocationRoleBoundary(invocation({ phase: "meeting" })),
    /phd_student.*review_gate/,
  );
  assert.throws(
    () => validateInvocationRoleBoundary(invocation({ role: "postdoc", phase: "postdoc_exchange" })),
    /specialty_domain/,
  );
});

test("server-selected research members may run task clarification", () => {
  for (const role of ["master_student", "phd_student", "postdoc"]) {
    assert.doesNotThrow(() => validateInvocationRoleBoundary(invocation({
      phase: "task_clarification",
      role,
    })));
  }
});

test("native prompt carries the frozen ForumMind role boundary", () => {
  const prompt = renderForumMindSystemPrompt({
    agent_id: "agent-phd-1",
    role: "phd_student",
    phase: "review_gate",
    profile_version: "v1",
    responsibilities: ["指出反例、可推翻条件和缺失观察"],
    phase_rules: ["只能输出审查意见"],
    allowed_tools: [],
    forbidden_actions: ["pi_decision", "formal_memory_write"],
    data_space: "synthetic",
    output_contract: "review_gate",
    safety_rules: ["no_formal_memory_write"],
  });

  assert.match(prompt, /phd_student/);
  assert.match(prompt, /review_gate/);
  assert.match(prompt, /formal_memory_write/);
  assert.doesNotMatch(prompt, /coding assistant operating/i);
});
