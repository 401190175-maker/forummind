import { test } from "node:test";
import assert from "node:assert/strict";
import { createForumMindSession, type FoamSessionManagerLike, type PiSdkLike } from "../src/session-factory.js";
import type { AgentInvocation } from "../src/contracts.js";

function fakeInvocation(overrides: Partial<AgentInvocation> = {}): AgentInvocation {
  return {
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
    ...overrides,
  };
}

function createFakePiSdk(): PiSdkLike {
  class FakeLoader {
    constructor(public readonly options: Record<string, unknown>) {}
    async reload(): Promise<void> {}
  }
  const manager = (persisted: boolean) => ({
    isPersisted: () => persisted,
    getCwd: () => "C:/forummind/runtime",
  });
  return {
    DefaultResourceLoader: FakeLoader,
    SessionManager: {
      inMemory: () => manager(false),
      create: () => manager(true),
    },
    createAgentSession: async (options) => ({
      session: {
        sessionId: "sess-1",
        systemPrompt: "ForumMind Agent",
        dispose: () => undefined,
        abort: async () => undefined,
        sessionManager: options.sessionManager as FoamSessionManagerLike,
      },
    }),
  };
}

test("session factory removes coding defaults and uses explicit tools", async () => {
  const session = await createForumMindSession(fakeInvocation(), {
    sdk: createFakePiSdk(),
    storage: "memory",
  });
  assert.match(session.systemPrompt, /ForumMind Agent/);
  assert.doesNotMatch(session.systemPrompt, /expert coding assistant operating inside pi/i);
  assert.deepEqual(session.activeToolNames, ["foam_memory_query"]);
  assert.equal(session.sessionManager.isPersisted(), false);
});

test("session factory passes the configured SDK model runtime to the session", async () => {
  const sdk = createFakePiSdk();
  const originalCreateSession = sdk.createAgentSession;
  const sdkRuntime = { kind: "configured-sdk-runtime" };
  let capturedRuntime: unknown;
  sdk.createAgentSession = async (options) => {
    capturedRuntime = options.modelRuntime;
    return originalCreateSession(options);
  };

  const modelRuntime = {
    resolve: async () => ({ id: "model" }),
    getRuntime: async () => sdkRuntime,
  };

  await createForumMindSession(fakeInvocation(), {
    sdk,
    storage: "memory",
    modelRuntime,
  });

  assert.equal(capturedRuntime, sdkRuntime);
});
