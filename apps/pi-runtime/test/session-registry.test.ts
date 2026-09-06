import { test } from "node:test";
import assert from "node:assert/strict";
import { SessionRegistry } from "../src/session-registry.js";
import type { AgentInvocation } from "../src/contracts.js";
import type { FoamSessionManagerLike } from "../src/session-factory.js";
import { createFakePiSdk } from "./support.js";

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

test("sessions from different scopes cannot be reused", async () => {
  const registry = new SessionRegistry({ storage: "memory", sdk: createFakePiSdk() });
  const first = await registry.open(fakeInvocation({ group_chat_id: "gc-1", agent_id: "a-1" }));
  await assert.rejects(() => registry.assertOwnership(first.sessionId, {
    group_chat_id: "gc-2", agent_id: "a-1", run_id: "run-2",
  }));
});

test("sessions with the same invocation id cannot cross task or document scope", async () => {
  const registry = new SessionRegistry({ storage: "memory", sdk: createFakePiSdk() });
  const first = await registry.open(fakeInvocation({
    invocation_id: "shared-invocation",
    task_id: "task-1",
    document_scope: ["doc-1"],
  }));

  const second = await registry.open(fakeInvocation({
    invocation_id: "shared-invocation",
    task_id: "task-2",
    document_scope: ["doc-2"],
  }));

  assert.notEqual(second.sessionId, first.sessionId);
  await assert.rejects(
    () => registry.assertOwnership(first.sessionId, fakeInvocation({
      invocation_id: "shared-invocation",
      task_id: "task-2",
      document_scope: ["doc-2"],
    })),
    /task_id/,
  );
});

test("persistent sessions with the same invocation id use task-isolated directories", async () => {
  const registry = new SessionRegistry({ storage: "persistent", sdk: createFakePiSdk() });
  const first = await registry.open(fakeInvocation({
    invocation_id: "shared-invocation",
    task_id: "task-1",
    document_scope: ["doc-1"],
  }));
  await registry.close(first.sessionId);

  const second = await registry.open(fakeInvocation({
    invocation_id: "shared-invocation",
    task_id: "task-2",
    document_scope: ["doc-2"],
  }));

  assert.notEqual(first.sessionManager.getSessionDir?.(), second.sessionManager.getSessionDir?.());
});

test("persistent sessions with the same task and invocation use document-isolated directories", async () => {
  const registry = new SessionRegistry({ storage: "persistent", sdk: createFakePiSdk() });
  const first = await registry.open(fakeInvocation({
    invocation_id: "shared-invocation",
    task_id: "task-1",
    document_scope: ["doc-1"],
  }));
  await registry.close(first.sessionId);

  const second = await registry.open(fakeInvocation({
    invocation_id: "shared-invocation",
    task_id: "task-1",
    document_scope: ["doc-2"],
  }));

  assert.notEqual(first.sessionManager.getSessionDir?.(), second.sessionManager.getSessionDir?.());
});

test("retry invocation gets a separate session and settled sessions release capacity", async () => {
  const registry = new SessionRegistry({ maxConcurrencyPerGroup: 1, storage: "memory", sdk: createFakePiSdk() });
  const first = await registry.open(fakeInvocation({ invocation_id: "inv-1" }));
  await registry.settle(first.sessionId);

  const retry = await registry.open(fakeInvocation({ invocation_id: "inv-2" }));

  assert.notEqual(retry.sessionId, first.sessionId);
  await assert.rejects(() => registry.assertOwnership(first.sessionId, fakeInvocation({ invocation_id: "inv-2" })), /invocation_id/);
});

test("persistent retry invocation gets a separate session directory", async () => {
  const registry = new SessionRegistry({ storage: "persistent", sdk: createFakePiSdk() });
  const first = await registry.open(fakeInvocation({ invocation_id: "inv-1" }));
  await registry.close(first.sessionId);

  const retry = await registry.open(fakeInvocation({ invocation_id: "inv-2" }));
  const firstDir = first.sessionManager.getSessionDir?.();
  const retryDir = retry.sessionManager.getSessionDir?.();

  assert.notEqual(firstDir, retryDir);
});

test("session registry maps a completed JSON candidate into the invocation contract", async () => {
  const sdk = createFakePiSdk();
  const output = JSON.stringify({
    claim: "磷石膏存在与含水状态相关的最佳掺量",
    evidence_refs: ["chunk-1"],
    reasoning_summary: "文档记录了掺量与抗压强度的变化关系",
    uncertainty: "当前资料不足以证明普适因果关系",
    next_action: "补充不同含水状态下的对照试验",
  });
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-structured",
      systemPrompt: "ForumMind Agent",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      dispose: () => undefined,
      abort: async () => undefined,
      subscribe: (listener) => {
        listeners.push(listener);
        return () => undefined;
      },
      prompt: async () => {
        for (const listener of listeners) {
          listener({
            type: "message_update",
            assistantMessageEvent: { type: "thinking_delta", delta: "{\"scratch\":true}" },
          });
          listener({
            type: "message_update",
            assistantMessageEvent: { type: "text_delta", delta: output },
          });
          listener({ type: "agent_settled" });
        }
      },
    },
  });
  const invocation = fakeInvocation({
    output_contract: "research_claim",
    data_space: "desensitized_real",
    task_id: "task-1",
    document_scope: ["doc-1"],
    context: {},
  });
  const registry = new SessionRegistry({ storage: "memory", sdk });
  const managed = await registry.open(invocation);

  await managed.session.prompt?.(invocation.task);

  assert.deepEqual(invocation.context.structured_output, JSON.parse(output));
});

test("session registry normalizes a provider-shaped claim from the final assistant message", async () => {
  const sdk = createFakePiSdk();
  const output = JSON.stringify({
    claim: {
      judgment: "气泡失稳是主要机制",
      boundary: "适用于水泥基泡沫混凝土",
      prediction: "稳泡后孔径粗化会减弱",
      falsification: "若稳泡不影响强度则不支持",
    },
    evidence_refs: ["chunk-1"],
    reasoning_summary: "候选由一次授权检索支持",
    uncertainty: "仍需对照试验",
    next_action: "验证孔径分布",
  });
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-provider-shaped-claim",
      systemPrompt: "ForumMind Agent",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      dispose: () => undefined,
      abort: async () => undefined,
      subscribe: (listener) => {
        listeners.push(listener);
        return () => undefined;
      },
      prompt: async () => {
        for (const listener of listeners) {
          listener({
            type: "message_update",
            assistantMessageEvent: { type: "thinking_delta", delta: "ignored" },
          });
          listener({
            type: "message_end",
            message: {
              role: "assistant",
              content: [
                { type: "thinking", thinking: "ignored" },
                { type: "text", text: "```json\\n" + output + "\\n```" },
              ],
            },
          });
          listener({ type: "agent_settled" });
        }
      },
    },
  });
  const invocation = fakeInvocation({
    output_contract: "research_claim",
    data_space: "desensitized_real",
    task_id: "task-1",
    document_scope: ["doc-1"],
    context: {},
  });
  const registry = new SessionRegistry({ storage: "memory", sdk });
  const managed = await registry.open(invocation);

  await managed.session.prompt?.(invocation.task);

  const structuredOutput = invocation.context.structured_output as Record<string, unknown>;
  assert.equal(
    structuredOutput.claim,
    "判断：气泡失稳是主要机制\n适用边界：适用于水泥基泡沫混凝土\n可观察预测：稳泡后孔径粗化会减弱\n可推翻条件：若稳泡不影响强度则不支持",
  );
});

test("session registry normalizes applicable-boundary provider claims", async () => {
  const sdk = createFakePiSdk();
  const output = JSON.stringify({
    claim: {
      judgment: "初始含水率主要通过稀释水化固相影响强度",
      applicable_boundary: "适用于高液限疏浚淤泥水泥固化体系",
      prediction: {
        main: "提高含水率会降低同龄期抗压强度",
        distinguishing: "固定固相体积后该趋势应减弱",
      },
      falsification_condition: "控制固相体积后含水率不再影响强度",
    },
    evidence_refs: ["chunk-1"],
    reasoning_summary: "候选由一次授权检索支持",
    uncertainty: "仍需对照试验",
    next_action: "验证含水率梯度",
  });
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-applicable-boundary-claim",
      systemPrompt: "ForumMind Agent",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      dispose: () => undefined,
      abort: async () => undefined,
      subscribe: (listener) => {
        listeners.push(listener);
        return () => undefined;
      },
      prompt: async () => {
        for (const listener of listeners) {
          listener({
            type: "message_end",
            message: {
              role: "assistant",
              content: [{ type: "text", text: output }],
            },
          });
          listener({ type: "agent_settled" });
        }
      },
    },
  });
  const invocation = fakeInvocation({
    output_contract: "research_claim",
    data_space: "desensitized_real",
    task_id: "task-1",
    document_scope: ["doc-1"],
    context: {},
  });
  const registry = new SessionRegistry({ storage: "memory", sdk });
  const managed = await registry.open(invocation);

  await managed.session.prompt?.(invocation.task);

  const structuredOutput = invocation.context.structured_output as Record<string, unknown>;
  assert.equal(
    structuredOutput.claim,
    "判断：初始含水率主要通过稀释水化固相影响强度\n适用边界：适用于高液限疏浚淤泥水泥固化体系\n可观察预测：main：提高含水率会降低同龄期抗压强度\ndistinguishing：固定固相体积后该趋势应减弱\n可推翻条件：控制固相体积后含水率不再影响强度",
  );
});

test("session registry parses escaped review JSON with provider category arrays", async () => {
  const sdk = createFakePiSdk();
  const output = [
    "```json\\n",
    "{\\n",
    "  \\\"counterexample\\\": {\\\"items\\\": [\\\"反例：仅凭单一龄期无法排除养护差异\\\"]},\\n",
    "  \\\"falsification_condition\\\": {\\\"items\\\": [\\\"可推翻条件：对照试验不再出现该趋势\\\"]},\\n",
    "  \\\"missing_observation\\\": {\\\"items\\\": [\\\"缺失观察：尚无孔径分布的重复测量\\\"]}\\n",
    "}\\n",
    "```",
  ].join("");
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-escaped-review",
      systemPrompt: "ForumMind Agent",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      dispose: () => undefined,
      abort: async () => undefined,
      subscribe: (listener) => {
        listeners.push(listener);
        return () => undefined;
      },
      prompt: async () => {
        listeners.forEach((listener) => listener({
          type: "message_end",
          message: { role: "assistant", content: output },
        }));
        listeners.forEach((listener) => listener({ type: "agent_settled" }));
      },
    },
  });
  const invocation = fakeInvocation({
    phase: "review_gate",
    role: "phd_student",
    output_contract: "review_gate",
    context: {},
  });
  const registry = new SessionRegistry({ storage: "memory", sdk });
  const managed = await registry.open(invocation);

  await managed.session.prompt?.(invocation.task);

  assert.deepEqual(invocation.context.structured_output, {
    counterexample: { items: ["反例：仅凭单一龄期无法排除养护差异"] },
    falsification_condition: { items: ["可推翻条件：对照试验不再出现该趋势"] },
    missing_observation: { items: ["缺失观察：尚无孔径分布的重复测量"] },
    items: [
      { kind: "counterexample", content: "反例：仅凭单一龄期无法排除养护差异" },
      { kind: "falsification_condition", content: "可推翻条件：对照试验不再出现该趋势" },
      { kind: "missing_observation", content: "缺失观察：尚无孔径分布的重复测量" },
    ],
  });
});

test("session registry maps a clarification JSON response into its output contract", async () => {
  const sdk = createFakePiSdk();
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-task-clarification",
      systemPrompt: "ForumMind Agent",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      dispose: () => undefined,
      abort: async () => undefined,
      subscribe: (listener) => {
        listeners.push(listener);
        return () => undefined;
      },
      prompt: async () => {
        listeners.forEach((listener) => listener({
          type: "message_end",
          message: {
            role: "assistant",
            content: JSON.stringify({
              question: "请明确本次分析需要比较的样品范围？",
              question_id: "question-1",
            }),
          },
        }));
        listeners.forEach((listener) => listener({ type: "agent_settled" }));
      },
    },
  });
  const invocation = fakeInvocation({
    run_id: "clarification-1",
    task_id: "clarification-1",
    phase: "task_clarification",
    role: "phd_student",
    output_contract: "clarification_question",
    context: {},
  });
  const registry = new SessionRegistry({ storage: "memory", sdk });
  const managed = await registry.open(invocation);

  await managed.session.prompt?.(invocation.task);

  assert.deepEqual(invocation.context.structured_output, {
    question: "请明确本次分析需要比较的样品范围？",
    question_id: "question-1",
  });
});
