import assert from "node:assert/strict";
import { test } from "node:test";

import { loadConfig, sessionDirectory } from "../src/config.js";
import type { AgentInvocation } from "../src/contracts.js";
import { SessionRegistry } from "../src/session-registry.js";
import { createFakePiSdk } from "./support.js";

function invocation(overrides: Partial<AgentInvocation> = {}): AgentInvocation {
  return {
    invocation_id: "inv-1",
    run_id: "run-1",
    group_chat_id: "group-1",
    cycle: 1,
    phase: "independent_analysis",
    agent_id: "agent-ms-1",
    role: "master_student",
    profile_version: "v1",
    agent_instruction: "ForumMind AgentInstruction",
    task: "形成候选观点",
    input_refs: [],
    context: {},
    allowed_tools: [],
    output_contract: "claim_four_fields",
    data_space: "synthetic",
    safety_rules: ["no_formal_memory_write"],
    ...overrides,
  };
}

test("runtime never uses the default Pi session directory", () => {
  assert.throws(
    () => loadConfig({ PI_SESSION_ROOT: "C:/FoamMind/.pi/agent/sessions" }),
    /default Pi session directory/,
  );
});

test("session scope rejects traversal and keeps runtime directories under the root", () => {
  const config = loadConfig({
    PI_SESSION_ROOT: "C:/FoamMind/pi-sessions",
    PI_RUNTIME_CWD: "C:/FoamMind/pi-sessions/runtime-cwd",
  });
  assert.throws(
    () => sessionDirectory(config, { groupChatId: "..", runId: "run-1", agentId: "agent-1" }),
    /unsafe path segment/,
  );
  assert.throws(() => loadConfig({
    PI_SESSION_ROOT: "C:/FoamMind/pi-sessions",
    PI_RUNTIME_CWD: "C:/outside/runtime",
  }), /PI_RUNTIME_CWD/);
});

test("parallelism is bounded per group", async () => {
  const registry = new SessionRegistry({
    maxConcurrencyPerGroup: 2,
    storage: "memory",
    sdk: createFakePiSdk(),
  });
  const opens = [1, 2, 3].map((index) => registry.open(invocation({
    invocation_id: `inv-${index}`,
    run_id: `run-${index}`,
    agent_id: `agent-ms-${index}`,
  })));

  await assert.rejects(Promise.all(opens), /concurrency limit/);
});
