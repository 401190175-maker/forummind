import type { AgentInvocation, RuntimeEvent, SessionRecord } from "./contracts.js";
import { loadConfig, type RuntimeConfig } from "./config.js";
import { adaptPiEvent } from "./events/pi-event-adapter.js";
import { RuntimeEventLog, identityDraft } from "./events/event-log.js";
import {
  SessionRegistry,
  type ManagedSession,
  type RegistryOptions,
} from "./session-registry.js";
import { ForumMindModelRuntime } from "./model-runtime.js";
import { buildForumMindTools, HttpToolGateway, type ToolGateway } from "./tools/foam-tool-adapter.js";

export type RuntimeHealth = {
  configured: boolean;
  provider: string;
  model: string;
  reachable: boolean;
  latency_ms: number;
  error_code: string;
};

type SessionState = {
  invocation: AgentInvocation;
  managed: ManagedSession;
  log: RuntimeEventLog;
  unsubscribe?: () => void;
  content: string;
  resultTooLarge: boolean;
  toolCalls: number;
  toolLimitExceeded: boolean;
  prompting: boolean;
  createdAt: number;
};

export type NativePiServiceOptions = {
  config?: RuntimeConfig;
  registry?: SessionRegistry;
  registryOptions?: RegistryOptions;
  gateway?: ToolGateway;
  providerProbe?: (config: RuntimeConfig) => Promise<ProviderProbeResult>;
};

type ProviderProbeResult = {
  reachable: boolean;
  latency_ms: number;
  error_code: string;
};

export class NativePiService {
  readonly config: RuntimeConfig;
  readonly registry: SessionRegistry;
  private readonly states = new Map<string, SessionState>();
  private readonly providerProbe: (config: RuntimeConfig) => Promise<ProviderProbeResult>;
  private readonly modelRuntime?: ForumMindModelRuntime;
  private providerHealth: RuntimeHealth;

  constructor(options: NativePiServiceOptions = {}) {
    this.config = options.config ?? loadConfig();
    this.providerProbe = options.providerProbe ?? probeOpenAiCompatibleProvider;
    this.providerHealth = initialHealth(this.config);
    const gateway = options.gateway ?? new HttpToolGateway(this.config.controlPlaneUrl, this.config.runtimeToken);
    if (options.registry) {
      this.registry = options.registry;
    } else {
      const modelRuntime = options.registryOptions?.modelRuntime ?? new ForumMindModelRuntime(this.config);
      this.modelRuntime = modelRuntime instanceof ForumMindModelRuntime ? modelRuntime : undefined;
      this.registry = new SessionRegistry({
        ...(options.registryOptions ?? {}),
        modelRuntime,
        storage: options.registryOptions?.storage ?? "persistent",
        maxConcurrencyPerGroup: options.registryOptions?.maxConcurrencyPerGroup ?? this.config.maxConcurrencyPerGroup,
        toolFactory: options.registryOptions?.toolFactory ?? ((invocation) => {
          const tools = buildForumMindTools(invocation, gateway);
          return { tools, activeToolNames: tools.map((tool) => tool.name) };
        }),
      });
    }
  }

  async createSession(invocation: AgentInvocation): Promise<SessionRecord> {
    const managed = await this.registry.open(invocation);
    let state = this.states.get(managed.sessionId);
    if (!state) {
      state = {
        invocation,
        managed,
        log: new RuntimeEventLog(this.config.maxSseBuffer),
        content: "",
        resultTooLarge: false,
        toolCalls: 0,
        toolLimitExceeded: false,
        prompting: false,
        createdAt: Date.now() / 1000,
      };
      state.unsubscribe = managed.session.subscribe?.((raw) => this.onPiEvent(state!, raw));
      this.states.set(managed.sessionId, state);
    } else {
      await this.registry.assertOwnership(managed.sessionId, invocation);
      state.invocation = invocation;
    }
    return this.sessionRecord(state);
  }

  async prompt(sessionId: string, invocation?: AgentInvocation): Promise<{ accepted: boolean; cursor: number; error?: string }> {
    const state = this.require(sessionId);
    if (invocation) await this.registry.assertOwnership(sessionId, invocation);
    if (state.prompting) return { accepted: false, cursor: state.log.latestCursor(), error: "prompt already running" };
    state.prompting = true;
    const current = invocation ?? state.invocation;
    if (!state.log.list().some((event) => event.invocation_id === current.invocation_id && event.type === "agent_started")) {
      state.log.append(identityDraft(current, sessionId, "agent_started"));
    }
    try {
      await withTimeout(
        state.managed.session.prompt?.(renderInvocationPrompt(current)) ?? Promise.resolve(),
        this.config.promptTimeoutMs,
      );
      if (state.resultTooLarge) {
        const error = "result exceeds configured byte limit";
        state.log.append(identityDraft(current, sessionId, "agent_failed", { error, error_code: "result_too_large" }));
        return { accepted: false, cursor: state.log.latestCursor(), error };
      }
      if (state.toolLimitExceeded) {
        const error = "tool call limit exceeded";
        state.log.append(identityDraft(current, sessionId, "agent_failed", { error, error_code: "tool_limit" }));
        return { accepted: false, cursor: state.log.latestCursor(), error };
      }
      if (!state.log.hasSettled(current.invocation_id)) {
        this.appendSettled(state, current);
      }
      return { accepted: true, cursor: state.log.latestCursor() };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      state.log.append(identityDraft(current, sessionId, "agent_failed", { error: message, error_code: "prompt_failed" }));
      return { accepted: false, cursor: state.log.latestCursor(), error: message };
    } finally {
      state.prompting = false;
    }
  }

  async steer(sessionId: string, message: string): Promise<{ accepted: boolean; cursor: number }> {
    const state = this.require(sessionId);
    await state.managed.session.steer?.(message);
    return { accepted: true, cursor: state.log.latestCursor() };
  }

  async followUp(sessionId: string, message: string): Promise<{ accepted: boolean; cursor: number }> {
    const state = this.require(sessionId);
    await state.managed.session.followUp?.(message);
    return { accepted: true, cursor: state.log.latestCursor() };
  }

  async abort(sessionId: string): Promise<{ aborted: boolean; cursor: number }> {
    const state = this.require(sessionId);
    await this.registry.abort(sessionId);
    if (!state.log.hasSettled(state.invocation.invocation_id)) {
      state.log.append(identityDraft(state.invocation, sessionId, "agent_aborted", { error_code: "aborted" }));
    }
    return { aborted: true, cursor: state.log.latestCursor() };
  }

  events(sessionId: string, after = 0): RuntimeEvent[] {
    return this.require(sessionId).log.list(after);
  }

  async dispose(sessionId: string): Promise<{ disposed: boolean }> {
    const state = this.require(sessionId);
    state.unsubscribe?.();
    await this.registry.close(sessionId);
    this.states.delete(sessionId);
    return { disposed: true };
  }

  async checkProvider(): Promise<RuntimeHealth> {
    const result = await this.providerProbe(this.config);
    this.providerHealth = {
      ...this.providerHealth,
      reachable: result.reachable,
      latency_ms: result.latency_ms,
      error_code: result.error_code,
    };
    return this.providerHealth;
  }

  async close(): Promise<void> {
    for (const state of this.states.values()) state.unsubscribe?.();
    await this.registry.closeAll();
    this.states.clear();
    await this.modelRuntime?.dispose();
  }

  health(): Record<string, unknown> {
    return { ...this.providerHealth, service: "forummind-pi-runtime", sessions: this.states.size };
  }

  private onPiEvent(state: SessionState, raw: unknown): void {
    const draft = adaptPiEvent(raw, state.invocation, state.managed.sessionId);
    if (!draft) return;
    if (draft.type === "text_delta") {
      const delta = draft.payload.content_delta;
      if (typeof delta === "string") {
        const next = state.content + delta;
        if (Buffer.byteLength(next, "utf8") > this.config.maxResultBytes) {
          state.resultTooLarge = true;
        } else {
          state.content = next;
        }
      }
    }
    if (draft.type === "text_completed" && !state.content) {
      const content = draft.payload.content;
      if (typeof content === "string") {
        if (Buffer.byteLength(content, "utf8") > this.config.maxResultBytes) {
          state.resultTooLarge = true;
        } else {
          state.content = content;
        }
      }
    }
    if (draft.type === "tool_started") {
      state.toolCalls += 1;
      if (state.toolCalls > this.config.maxToolCallsPerRun) state.toolLimitExceeded = true;
    }
    if (draft.type === "agent_settled") {
      draft.payload = { result: this.result(state) };
    }
    state.log.append(draft);
  }

  private appendSettled(state: SessionState, invocation: AgentInvocation): void {
    state.log.append({
      ...identityDraft(invocation, state.managed.sessionId, "agent_settled"),
      payload: { result: this.result(state) },
    });
  }

  private result(state: SessionState): Record<string, unknown> {
    const structured = state.invocation.context.structured_output;
    return {
      agent_id: state.invocation.agent_id,
      status: "ok",
      content: state.content,
      structured_output: structured && typeof structured === "object" && !Array.isArray(structured) ? structured : {},
      tool_calls: [], runtime_state_ref: state.managed.sessionId,
      warnings: [], error: "", error_code: "", data_space: state.invocation.data_space,
    };
  }

  private sessionRecord(state: SessionState): SessionRecord {
    return {
      session_id: state.managed.sessionId,
      session_scope: `${state.invocation.group_chat_id}/${state.invocation.run_id}/${state.invocation.agent_id}`,
      group_chat_id: state.invocation.group_chat_id,
      run_id: state.invocation.run_id,
      agent_id: state.invocation.agent_id,
      phase: state.invocation.phase,
      data_space: state.invocation.data_space,
      cursor: state.log.latestCursor(),
      status: state.prompting ? "active" : "active",
      persisted: state.managed.sessionManager.isPersisted(),
    };
  }

  private require(sessionId: string): SessionState {
    const state = this.states.get(sessionId);
    if (!state) throw new Error(`session not found: ${sessionId}`);
    return state;
  }
}

function renderInvocationPrompt(invocation: AgentInvocation): string {
  const taskContext = invocation.context.task_context;
  const readOnlyContext = { ...invocation.context };
  if (taskContext && typeof taskContext === "object" && !Array.isArray(taskContext)) {
    readOnlyContext.task_context = {
      ...(taskContext as Record<string, unknown>),
      output_contract: invocation.output_contract,
    };
  }
  const context = {
    context: readOnlyContext,
    input_refs: invocation.input_refs,
    task_id: invocation.task_id ?? "",
    document_scope: invocation.document_scope ?? [],
    data_space: invocation.data_space,
    output_contract: invocation.output_contract,
  };
  return [
    invocation.task,
    "ForumMind 只读任务上下文（不得据此执行写入或改变流程）：",
    JSON.stringify(context, null, 2),
    `本次 Session 唯一输出契约：${invocation.output_contract}（以此为准）`,
    outputContractGuide(invocation.output_contract),
  ].join("\n\n");
}

function outputContractGuide(outputContract: string): string {
  const guides: Record<string, string> = {
    clarification_question: "最终只能输出一个 JSON 对象，不要输出分析过程、Markdown、代码围栏或回显上下文；顶层必须包含 question、question_id 两个非空文本字段，question_id 使用 question-<当前 question_number>。",
    claim_four_fields: "最终只能输出一个 JSON 对象，不要输出分析过程、Markdown、代码围栏或回显上下文；顶层必须包含 statement、boundary、prediction、falsification_condition 四个非空文本字段。",
    research_claim: "最终只能输出一个 JSON 对象，不要输出分析过程、Markdown、代码围栏或回显上下文；顶层必须包含 claim、evidence_refs、reasoning_summary、uncertainty、next_action，evidence_refs 必须是非空 chunk_id 字符串数组。",
    review_gate: "最终只能输出一个 JSON 对象，不要输出分析过程、Markdown、代码围栏或回显上下文；顶层必须包含 items 数组，items 至少分别包含 kind 为 counterexample、falsification_condition、missing_observation 的非空 content。",
    postdoc_synthesis: "最终只能输出一个 JSON 对象，不要输出分析过程、Markdown、代码围栏或回显上下文；顶层必须包含 summary、recommendations、limitations、open_questions。",
    revision_dispositions: "最终只能输出一个 JSON 对象，不要输出分析过程、Markdown、代码围栏或回显上下文；顶层必须包含 dispositions 数组。",
  };
  return guides[outputContract] ?? "最终只能输出一个 JSON 对象，不要输出分析过程、Markdown、代码围栏或回显上下文。";
}

function initialHealth(config: RuntimeConfig): RuntimeHealth {
  const configured = Boolean(config.provider.trim() && config.model.trim() && config.baseUrl.trim() && config.apiKey.trim());
  return {
    configured,
    provider: config.provider,
    model: config.model,
    reachable: false,
    latency_ms: 0,
    error_code: configured ? "not_checked" : "provider_unconfigured",
  };
}

async function probeOpenAiCompatibleProvider(config: RuntimeConfig): Promise<ProviderProbeResult> {
  const started = performance.now();
  const latency = () => Math.max(Math.round(performance.now() - started), 0);
  if (!config.baseUrl.trim() || !config.model.trim() || !config.apiKey.trim()) {
    return { reachable: false, latency_ms: latency(), error_code: "provider_unconfigured" };
  }
  const endpoint = config.baseUrl.replace(/\/$/, "").endsWith("/chat/completions")
    ? config.baseUrl
    : `${config.baseUrl.replace(/\/$/, "")}/chat/completions`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Math.max(config.promptTimeoutMs, 1000));
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: config.model,
        messages: [{ role: "user", content: "Return the JSON object {\"ok\":true}." }],
        max_tokens: 8,
        temperature: 0,
      }),
      signal: controller.signal,
    });
    if (response.status === 401 || response.status === 403) {
      return { reachable: false, latency_ms: latency(), error_code: "provider_auth" };
    }
    if (response.status === 429) {
      return { reachable: false, latency_ms: latency(), error_code: "provider_rate_limited" };
    }
    if (response.status >= 500) {
      return { reachable: false, latency_ms: latency(), error_code: "provider_unavailable" };
    }
    if (!response.ok) {
      return { reachable: false, latency_ms: latency(), error_code: "provider_protocol" };
    }
    let body: unknown;
    try {
      body = await response.json() as unknown;
    } catch {
      return { reachable: false, latency_ms: latency(), error_code: "provider_protocol" };
    }
    const completion = extractCompletionContent(body);
    if (completion.kind === "malformed") {
      return { reachable: false, latency_ms: latency(), error_code: "provider_protocol" };
    }
    return {
      reachable: completion.kind === "content",
      latency_ms: latency(),
      error_code: completion.kind === "content" ? "" : "provider_empty",
    };
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    return {
      reachable: false,
      latency_ms: latency(),
      error_code: name === "AbortError" ? "provider_timeout" : "provider_unavailable",
    };
  } finally {
    clearTimeout(timeout);
  }
}

type CompletionContent =
  | { kind: "content"; value: string }
  | { kind: "empty" }
  | { kind: "malformed" };

function extractCompletionContent(value: unknown): CompletionContent {
  if (!value || typeof value !== "object" || !("choices" in value)) return { kind: "malformed" };
  const choices = (value as { choices?: unknown }).choices;
  if (!Array.isArray(choices)) return { kind: "malformed" };
  if (choices.length === 0) return { kind: "empty" };
  const message = choices[0];
  if (!message || typeof message !== "object" || !("message" in message)) return { kind: "malformed" };
  const nested = (message as { message?: unknown }).message;
  if (!nested || typeof nested !== "object" || !("content" in nested)) return { kind: "malformed" };
  const content = (nested as { content?: unknown }).content;
  if (typeof content !== "string") return { kind: "malformed" };
  const trimmed = content.trim();
  return trimmed ? { kind: "content", value: trimmed } : { kind: "empty" };
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => reject(new Error("prompt timeout")), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
