import { test } from "node:test";
import assert from "node:assert/strict";
import type { AgentInvocation } from "../src/contracts.js";
import { buildForumMindTools, type ToolGateway } from "../src/tools/foam-tool-adapter.js";

function fakeInvocation(overrides: Partial<AgentInvocation> = {}): AgentInvocation {
  return {
    invocation_id: "inv-1", run_id: "run-1", group_chat_id: "gc-1", cycle: 1,
    phase: "independent_analysis", agent_id: "agent-ms-1", role: "master_student",
    profile_version: "v1", agent_instruction: "instruction", task: "task", input_refs: ["mem-1"],
    context: {}, allowed_tools: ["memory.query"], output_contract: "claim_four_fields",
    data_space: "synthetic", safety_rules: [], ...overrides,
  };
}

function fakeGateway(calls: Record<string, unknown>[] = []): ToolGateway {
  return {
    async execute(request, signal) {
      calls.push(request);
      assert.equal(signal?.aborted, false);
      return { status: "ok", payload: { items: [] }, source_refs: ["mem-1"], data_space: "synthetic" };
    },
  };
}

test("native tools expose only the invocation allowlist", () => {
  const tools = buildForumMindTools(fakeInvocation({ allowed_tools: ["memory.query"] }), fakeGateway());
  assert.deepEqual(tools.map((tool) => tool.name), ["foam_memory_query"]);
  assert.equal(tools.some((tool) => tool.name === "bash"), false);
});

test("tool adapter forwards identity and abort signal", async () => {
  const calls: Record<string, unknown>[] = [];
  const tool = buildForumMindTools(fakeInvocation(), fakeGateway(calls))[0];
  const result = await tool.execute("call-1", { query: "孔结构" }, new AbortController().signal, undefined, {} as never);
  assert.equal(calls[0].agent_id, "agent-ms-1");
  assert.equal((result.details as { status: string }).status, "ok");
});

test("aborted tool calls never reach the gateway", async () => {
  const calls: Record<string, unknown>[] = [];
  const tool = buildForumMindTools(fakeInvocation(), fakeGateway(calls))[0];
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    tool.execute("call-1", { query: "x" }, controller.signal, undefined, {} as never),
    /aborted/,
  );
  assert.equal(calls.length, 0);
});

test("native adapter maps real knowledge search without exposing trusted scope fields", async () => {
  const calls: Record<string, unknown>[] = [];
  const tool = buildForumMindTools(fakeInvocation({
    allowed_tools: ["knowledge.search"],
    data_space: "desensitized_real",
    context: { task_id: "task-1", allowed_document_ids: ["doc-1"] },
  }), fakeGateway(calls))[0];

  assert.equal(tool.name, "foam_knowledge_search");
  assert.deepEqual(Object.keys((tool.parameters as { properties: Record<string, unknown> }).properties), [
    "query", "document_ids", "limit",
  ]);
  await tool.execute("call-real", { query: "strength" }, new AbortController().signal, undefined, {} as never);
  assert.equal(calls[0].name, "knowledge.search");
  assert.equal((calls[0].arguments as Record<string, unknown>).task_id, undefined);
});

test("native adapter keeps real source refs visible when gateway payload is truncated", async () => {
  const sourceRefs = ["chunk-a", "chunk-b"];
  const gateway: ToolGateway = {
    async execute() {
      return {
        status: "limit_exceeded",
        payload: { truncated: true, size_bytes: 25265 },
        source_refs: sourceRefs,
        data_space: "desensitized_real",
        error_code: "result_size_exceeded",
      };
    },
  };
  const tool = buildForumMindTools(fakeInvocation({
    allowed_tools: ["knowledge.search"],
    data_space: "desensitized_real",
  }), gateway)[0];

  const result = await tool.execute(
    "call-truncated",
    { query: "strength" },
    new AbortController().signal,
    undefined,
    {} as never,
  );
  const visible = JSON.parse((result.content[0] as { text: string }).text) as Record<string, unknown>;
  assert.deepEqual(visible.truncated, true);
  assert.deepEqual(visible.source_refs, sourceRefs);
  assert.deepEqual(visible.error_code, "result_size_exceeded");
});
