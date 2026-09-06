import { test } from "node:test";
import assert from "node:assert/strict";
import { parseInvocation, parseRuntimeEvent } from "../src/contracts.js";

test("invocation requires ForumMind identity and data space", () => {
  assert.throws(() => parseInvocation({ agent_id: "agent-ms-1" }));
  const value = parseInvocation({
    invocation_id: "inv-1",
    run_id: "run-1",
    group_chat_id: "gc-1",
    cycle: 1,
    phase: "independent_analysis",
    agent_id: "agent-ms-1",
    role: "master_student",
    profile_version: "v1",
    agent_instruction: "ForumMind AgentInstruction",
    task: "形成 Claim 草案",
    input_refs: [],
    context: {},
    allowed_tools: ["memory.query"],
    output_contract: "claim_four_fields",
    data_space: "synthetic",
    safety_rules: ["no_formal_memory_write"],
  });
  assert.equal(value.agent_id, "agent-ms-1");
});

test("event cursor and identity are mandatory", () => {
  assert.throws(() => parseRuntimeEvent({ type: "text_delta" }));
});

test("real invocation and events preserve task document scope", () => {
  const value = parseInvocation({
    invocation_id: "inv-real", run_id: "run-real", group_chat_id: "gc-real", cycle: 1,
    phase: "independent_analysis", agent_id: "agent-real", role: "master_student",
    profile_version: "v1", agent_instruction: "instruction", task: "形成候选 Claim",
    input_refs: [], context: {}, allowed_tools: ["knowledge.search"],
    output_contract: "research_claim", data_space: "desensitized_real",
    task_id: "task-real", document_scope: ["doc-real"], safety_rules: ["candidate_only"],
  });
  const event = parseRuntimeEvent({
    event_id: "event-real", cursor: 1, session_id: "session-real",
    invocation_id: "inv-real", run_id: "run-real", group_chat_id: "gc-real",
    agent_id: "agent-real", phase: "independent_analysis", type: "text_delta",
    payload: { content_delta: "候选" }, data_space: "desensitized_real",
    task_id: "task-real", document_scope: ["doc-real"], timestamp: 1,
  });
  assert.equal(value.task_id, "task-real");
  assert.deepEqual(value.document_scope, ["doc-real"]);
  assert.equal(event.task_id, "task-real");
  assert.deepEqual(event.document_scope, ["doc-real"]);
});

test("parser accepts the structured ForumMind instruction payload", () => {
  const value = parseInvocation({
    invocation_id: "inv-object", run_id: "run-object", group_chat_id: "gc-object", cycle: 1,
    phase: "independent_analysis", agent_id: "agent-object", role: "master_student",
    profile_version: "v1", agent_instruction: { agent_id: "agent-object", output_contract: "research_claim" },
    task: "形成候选 Claim", input_refs: [], context: {}, allowed_tools: [],
    output_contract: "research_claim", data_space: "desensitized_real",
    task_id: "task-object", document_scope: ["doc-object"], safety_rules: ["candidate_only"],
  });
  assert.match(value.agent_instruction, /agent-object/);
});
