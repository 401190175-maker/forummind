import { test } from "node:test";
import assert from "node:assert/strict";
import { loadConfig, type RuntimeConfig } from "../src/config.js";
import type { AgentInvocation } from "../src/contracts.js";
import { createRuntimeHttpServer } from "../src/http-server.js";
import { NativePiService } from "../src/service.js";
import { SessionRegistry } from "../src/session-registry.js";
import type { FoamSessionManagerLike, PiSdkLike } from "../src/session-factory.js";

function invocation(overrides: Partial<AgentInvocation> = {}): AgentInvocation {
  return {
    invocation_id: "inv-1", run_id: "run-1", group_chat_id: "gc-1", cycle: 1,
    phase: "independent_analysis", agent_id: "agent-ms-1", role: "master_student",
    profile_version: "v1", agent_instruction: "instruction", task: "task", input_refs: [],
    context: {}, allowed_tools: [], output_contract: "free_text", data_space: "synthetic",
    safety_rules: [], ...overrides,
  };
}

function fakeSdk(): PiSdkLike {
  let nextId = 0;
  class Loader { constructor(public readonly options: Record<string, unknown>) {} async reload() {} }
  const manager = (): FoamSessionManagerLike => ({ isPersisted: () => false, getCwd: () => process.cwd() });
  return {
    DefaultResourceLoader: Loader,
    SessionManager: { inMemory: manager, create: manager },
    createAgentSession: async (options) => {
      const listeners = new Set<(event: unknown) => void>();
      const session = {
        sessionId: `sess-${++nextId}`,
        sessionManager: options.sessionManager as FoamSessionManagerLike,
        systemPrompt: "ForumMind Agent",
        subscribe(listener: (event: unknown) => void) { listeners.add(listener); return () => listeners.delete(listener); },
        async prompt() {
          const emit = (event: unknown) => { for (const listener of listeners) listener(event); };
          emit({ type: "agent_start" });
          emit({ type: "turn_start", turnIndex: 0, timestamp: 1 });
          emit({ type: "tool_execution_start", toolCallId: "call-1", toolName: "foam_memory_query", args: { query: "x" } });
          emit({ type: "tool_execution_end", toolCallId: "call-1", toolName: "foam_memory_query", args: { query: "x" }, result: {}, isError: false });
          emit({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "candidate" } });
          emit({ type: "message_end", message: { role: "assistant", content: "candidate" } });
          emit({ type: "turn_end", turnIndex: 0, message: {}, toolResults: [] });
        },
        async abort() {},
        dispose() {},
      };
      return { session };
    },
  };
}

function service(): NativePiService {
  const config = loadConfig({ PI_RUNTIME_TOKEN: "secret", PI_SESSION_ROOT: `${process.cwd()}/.runtime/test-sessions` });
  const registry = new SessionRegistry({ storage: "memory", sdk: fakeSdk(), modelRuntime: { resolve: async () => undefined } });
  return new NativePiService({ config, registry });
}

test("settled is emitted after all tool and turn events", async () => {
  const runtime = service();
  const session = await runtime.createSession(invocation());
  await runtime.prompt(session.session_id, invocation());
  assert.deepEqual(runtime.events(session.session_id).map((event) => event.type), [
    "agent_started", "turn_started", "tool_started", "tool_completed",
    "text_delta", "text_completed", "turn_completed", "agent_settled",
  ]);
  const settled = runtime.events(session.session_id).at(-1)!;
  assert.equal((settled.payload.result as Record<string, unknown>).content, "candidate");
});

test("user message_end is not captured as an agent candidate", async () => {
  const sdk = fakeSdk();
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-user-message-filter",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      systemPrompt: "ForumMind Agent",
      subscribe(listener) {
        listeners.push(listener);
        return () => undefined;
      },
      async prompt() {
        listeners.forEach((listener) => listener({ type: "agent_start" }));
        listeners.forEach((listener) => listener({
          type: "message_end",
          message: { role: "user", content: "echoed input context" },
        }));
        listeners.forEach((listener) => listener({
          type: "message_update",
          assistantMessageEvent: { type: "text_delta", delta: "assistant answer" },
        }));
        listeners.forEach((listener) => listener({
          type: "message_end",
          message: { role: "assistant", content: "assistant answer" },
        }));
      },
      async abort() {},
      dispose() {},
    },
  });
  const config = loadConfig({ PI_RUNTIME_TOKEN: "secret", PI_SESSION_ROOT: `${process.cwd()}/.runtime/user-message-filter-sessions` });
  const registry = new SessionRegistry({ storage: "memory", sdk, modelRuntime: { resolve: async () => undefined } });
  const runtime = new NativePiService({ config, registry });
  const session = await runtime.createSession(invocation());

  await runtime.prompt(session.session_id, invocation());

  const settled = runtime.events(session.session_id).at(-1)!;
  assert.equal((settled.payload.result as Record<string, unknown>).content, "assistant answer");
});

test("provider authentication errors terminate the invocation without a false settled result", async () => {
  const sdk = fakeSdk();
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-provider-auth-error",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      systemPrompt: "ForumMind Agent",
      subscribe(listener) {
        listeners.push(listener);
        return () => undefined;
      },
      async prompt() {
        listeners.forEach((listener) => listener({
          type: "message_end",
          message: {
            role: "assistant",
            content: [],
            stopReason: "error",
            errorMessage: "401: invalid_api_key",
          },
        }));
        listeners.forEach((listener) => listener({ type: "agent_settled" }));
      },
      async abort() {},
      dispose() {},
    },
  });
  const config = loadConfig({
    PI_RUNTIME_TOKEN: "secret",
    PI_SESSION_ROOT: `${process.cwd()}/.runtime/provider-auth-error-sessions`,
  });
  const registry = new SessionRegistry({
    storage: "memory",
    sdk,
    modelRuntime: { resolve: async () => undefined },
  });
  const runtime = new NativePiService({ config, registry });
  const session = await runtime.createSession(invocation());

  const response = await runtime.prompt(session.session_id, invocation());

  assert.equal(response.accepted, true);
  const terminal = runtime.events(session.session_id).filter((event) =>
    ["agent_failed", "agent_settled"].includes(event.type)
  );
  assert.deepEqual(terminal.map((event) => event.type), ["agent_failed"]);
  assert.equal(terminal[0].payload.error_code, "pi_auth");
  assert.equal(terminal[0].payload.error, "401: invalid_api_key");
});

test("prompt includes the invocation context needed by review and synthesis roles", async () => {
  const sdk = fakeSdk();
  let receivedPrompt = "";
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-context",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      systemPrompt: "ForumMind Agent",
      subscribe: () => () => undefined,
      async prompt(text: string) {
        receivedPrompt = text;
      },
      async abort() {},
      dispose() {},
    },
  });
  const config = loadConfig({ PI_RUNTIME_TOKEN: "secret", PI_SESSION_ROOT: `${process.cwd()}/.runtime/context-sessions` });
  const registry = new SessionRegistry({ storage: "memory", sdk, modelRuntime: { resolve: async () => undefined } });
  const runtime = new NativePiService({ config, registry });
  const review = invocation({
    phase: "review_gate",
    role: "phd_student",
    output_contract: "review_gate",
    input_refs: ["step-candidate-1"],
    context: { claims: [{ agent_id: "agent-ms-1", content: "candidate-marker" }] },
  });
  const session = await runtime.createSession(review);

  await runtime.prompt(session.session_id, review);

  assert.match(receivedPrompt, /candidate-marker/);
  assert.match(receivedPrompt, /step-candidate-1/);
});

test("prompt makes the current output contract authoritative over task context", async () => {
  const sdk = fakeSdk();
  let receivedPrompt = "";
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-contract-priority",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      systemPrompt: "ForumMind Agent",
      subscribe: () => () => undefined,
      async prompt(text: string) {
        receivedPrompt = text;
      },
      async abort() {},
      dispose() {},
    },
  });
  const config = loadConfig({ PI_RUNTIME_TOKEN: "secret", PI_SESSION_ROOT: `${process.cwd()}/.runtime/contract-priority-sessions` });
  const registry = new SessionRegistry({ storage: "memory", sdk, modelRuntime: { resolve: async () => undefined } });
  const review = invocation({
    phase: "review_gate",
    role: "phd_student",
    output_contract: "review_gate",
    context: { task_context: { output_contract: "research_claim", question: "review candidates" } },
  });
  const runtime = new NativePiService({ config, registry });
  const session = await runtime.createSession(review);

  await runtime.prompt(session.session_id, review);

  assert.match(receivedPrompt, /本次 Session 唯一输出契约：review_gate/);
  assert.doesNotMatch(receivedPrompt, /"output_contract": "research_claim"/);
  assert.match(receivedPrompt, /"output_contract": "review_gate"/);
  assert.match(receivedPrompt, /最终只能输出一个 JSON 对象/);
  assert.match(receivedPrompt, /items/);
  assert.match(receivedPrompt, /"output_contract": "review_gate"[\s\S]*最终只能输出一个 JSON 对象/);
});

test("clarification prompt names both required output fields", async () => {
  const sdk = fakeSdk();
  let receivedPrompt = "";
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-clarification-contract",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      systemPrompt: "ForumMind Agent",
      subscribe: () => () => undefined,
      async prompt(text: string) {
        receivedPrompt = text;
      },
      async abort() {},
      dispose() {},
    },
  });
  const config = loadConfig({
    PI_RUNTIME_TOKEN: "secret",
    PI_SESSION_ROOT: `${process.cwd()}/.runtime/clarification-contract-sessions`,
  });
  const registry = new SessionRegistry({
    storage: "memory",
    sdk,
    modelRuntime: { resolve: async () => undefined },
  });
  const clarification = invocation({
    phase: "task_clarification",
    role: "master_student",
    output_contract: "clarification_question",
    context: { question_number: 1 },
  });
  const runtime = new NativePiService({ config, registry });
  const session = await runtime.createSession(clarification);

  await runtime.prompt(session.session_id, clarification);

  assert.match(
    receivedPrompt,
    /顶层必须包含 question、question_id 两个非空文本字段/,
  );
});

test("reasoning deltas do not count toward the bounded candidate result", async () => {
  const sdk = fakeSdk();
  const listeners: Array<(event: unknown) => void> = [];
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-reasoning",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      systemPrompt: "ForumMind Agent",
      subscribe(listener) {
        listeners.push(listener);
        return () => undefined;
      },
      async prompt() {
        listeners.forEach((listener) => listener({
          type: "message_update",
          assistantMessageEvent: { type: "thinking_delta", delta: "long internal reasoning" },
        }));
        listeners.forEach((listener) => listener({
          type: "message_update",
          assistantMessageEvent: { type: "text_delta", delta: "ok" },
        }));
        listeners.forEach((listener) => listener({
          type: "message_end",
          message: { role: "assistant", content: "ok" },
        }));
      },
      async abort() {},
      dispose() {},
    },
  });
  const config = loadConfig({
    PI_RUNTIME_TOKEN: "secret",
    PI_SESSION_ROOT: `${process.cwd()}/.runtime/reasoning-sessions`,
    PI_MAX_RESULT_BYTES: "8",
  });
  const registry = new SessionRegistry({ storage: "memory", sdk, modelRuntime: { resolve: async () => undefined } });
  const runtime = new NativePiService({ config, registry });

  const session = await runtime.createSession(invocation());
  const result = await runtime.prompt(session.session_id, invocation());

  assert.equal(result.accepted, true);
  assert.equal((runtime.events(session.session_id).at(-1)?.payload.result as Record<string, unknown>).content, "ok");
});

test("default prompt budget allows a 150 second multi-turn provider run", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const sdk = fakeSdk();
  sdk.createAgentSession = async (options) => ({
    session: {
      sessionId: "sess-long-provider-run",
      sessionManager: options.sessionManager as FoamSessionManagerLike,
      systemPrompt: "ForumMind Agent",
      subscribe: () => () => undefined,
      async prompt() {
        await new Promise<void>((resolve) => setTimeout(resolve, 150_000));
      },
      async abort() {},
      dispose() {},
    },
  });
  const config = loadConfig({
    PI_RUNTIME_TOKEN: "secret",
    PI_SESSION_ROOT: `${process.cwd()}/.runtime/long-provider-run-sessions`,
  });
  const registry = new SessionRegistry({
    storage: "memory",
    sdk,
    modelRuntime: { resolve: async () => undefined },
  });
  const runtime = new NativePiService({ config, registry });
  const session = await runtime.createSession(invocation());

  const pending = runtime.prompt(session.session_id);
  t.mock.timers.tick(150_000);
  const result = await pending;

  assert.equal(result.accepted, true);
});

test("HTTP server rejects missing runtime token", async () => {
  const server = createRuntimeHttpServer(service());
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.equal(typeof address, "object");
  const response = await fetch(`http://127.0.0.1:${(address as { port: number }).port}/health`);
  assert.equal(response.status, 401);
  await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
});

test("HTTP server accepts an authenticated health request", async () => {
  const server = createRuntimeHttpServer(service());
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as { port: number };
  const response = await fetch(`http://127.0.0.1:${address.port}/health`, { headers: { "X-ForumMind-Runtime-Token": "secret" } });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).service, "forummind-pi-runtime");
  await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
});

test("HTTP server accepts a real-data task clarification session", async () => {
  const server = createRuntimeHttpServer(service());
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address() as { port: number };
    const response = await fetch(`http://127.0.0.1:${address.port}/v1/sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-ForumMind-Runtime-Token": "secret",
      },
      body: JSON.stringify(invocation({
        run_id: "clarification-1",
        task_id: "clarification-1",
        phase: "task_clarification",
        role: "master_student",
        data_space: "desensitized_real",
      })),
    });

    assert.equal(response.status, 200, await response.text());
  } finally {
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});
