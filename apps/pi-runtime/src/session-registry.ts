import type { AgentInvocation } from "./contracts.js";
import { createHash } from "node:crypto";
import { join } from "node:path";
import {
  createForumMindSession,
  type ManagedSession,
  type PiSdkLike,
  type SessionFactoryOptions,
  type ToolFactory,
} from "./session-factory.js";
import { loadConfig } from "./config.js";

export type { ManagedSession } from "./session-factory.js";

type ScopeIdentity = {
  group_chat_id: string;
  agent_id: string;
  run_id: string;
  invocation_id?: string;
  data_space?: string;
  task_id?: string;
  document_scope?: string[];
};

export type RegistryOptions = SessionFactoryOptions & {
  maxConcurrencyPerGroup?: number;
  sdk?: PiSdkLike;
};

export class SessionRegistry {
  private readonly sessions = new Map<string, ManagedSession>();
  private readonly scopes = new Map<string, ScopeIdentity>();
  private readonly outputCaptures = new Map<string, OutputCapture>();
  private readonly outputUnsubscribers = new Map<string, () => void>();
  private readonly options: RegistryOptions;
  private readonly maxConcurrencyPerGroup: number;
  private readonly activeByGroup = new Map<string, number>();
  private readonly pendingByGroup = new Map<string, number>();
  private readonly reservedSessions = new Set<string>();

  constructor(options: RegistryOptions = {}) {
    this.options = options;
    this.maxConcurrencyPerGroup = Number.isInteger(options.maxConcurrencyPerGroup) && (options.maxConcurrencyPerGroup ?? 0) > 0
      ? options.maxConcurrencyPerGroup!
      : 2;
  }

  async open(invocation: AgentInvocation): Promise<ManagedSession> {
    validateInvocationRoleBoundary(invocation);
    const key = scopeKey(invocation);
    const existingEntry = [...this.scopes.entries()]
      .find(([, scope]) => scopeKey(scope) === key);
    const existingSession = existingEntry ? this.sessions.get(existingEntry[0]) : undefined;
    if (existingSession) {
      await this.assertOwnership(existingSession.sessionId, invocation);
      return existingSession;
    }
    const group = invocation.group_chat_id;
    const inFlight = (this.pendingByGroup.get(group) ?? 0) + (this.activeByGroup.get(group) ?? 0);
    if (inFlight >= this.maxConcurrencyPerGroup) {
      throw new Error(`concurrency limit exceeded for group ${group}`);
    }
    this.pendingByGroup.set(group, (this.pendingByGroup.get(group) ?? 0) + 1);
    try {
      const session = await createForumMindSession(
        invocation,
        persistentInvocationOptions(invocation, this.options),
      );
      const prompt = session.session.prompt;
      if (prompt) {
        session.session.prompt = async (text: string) => {
          try {
            await prompt.call(session.session, text);
          } finally {
            await this.settle(session.sessionId);
          }
        };
      }
      const unsubscribe = session.session.subscribe?.((event) => {
        captureOutputEvent(this.outputCaptures.get(session.sessionId), event);
      });
      this.sessions.set(session.sessionId, session);
      this.outputCaptures.set(session.sessionId, { invocation, text: "" });
      if (unsubscribe) this.outputUnsubscribers.set(session.sessionId, unsubscribe);
      this.scopes.set(session.sessionId, {
        group_chat_id: group,
        run_id: invocation.run_id,
        agent_id: invocation.agent_id,
        invocation_id: invocation.invocation_id,
        data_space: invocation.data_space,
        task_id: invocation.task_id ?? "",
        document_scope: [...(invocation.document_scope ?? [])],
      });
      this.reservedSessions.add(session.sessionId);
      this.activeByGroup.set(group, (this.activeByGroup.get(group) ?? 0) + 1);
      return session;
    } finally {
      const pending = (this.pendingByGroup.get(group) ?? 1) - 1;
      if (pending > 0) this.pendingByGroup.set(group, pending);
      else this.pendingByGroup.delete(group);
    }
  }

  get(sessionId: string): ManagedSession | undefined {
    return this.sessions.get(sessionId);
  }

  async assertOwnership(sessionId: string, identity: ScopeIdentity | AgentInvocation): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (!session) throw new Error(`session not found: ${sessionId}`);
    const record = this.scopes.get(sessionId);
    if (!record) throw new Error(`session scope missing: ${sessionId}`);
    if (record.group_chat_id !== identity.group_chat_id) {
      throw new Error("session ownership mismatch: group_chat_id");
    }
    if (record.agent_id !== identity.agent_id) {
      throw new Error("session ownership mismatch: agent_id");
    }
    if (record.run_id !== identity.run_id) {
      throw new Error("session ownership mismatch: run_id");
    }
    if (identity.task_id !== undefined && record.task_id !== identity.task_id) {
      throw new Error("session ownership mismatch: task_id");
    }
    if (identity.document_scope !== undefined && !sameDocumentScope(record.document_scope, identity.document_scope)) {
      throw new Error("session ownership mismatch: document_scope");
    }
    if (identity.invocation_id !== undefined && record.invocation_id !== identity.invocation_id) {
      throw new Error("session ownership mismatch: invocation_id");
    }
    if (identity.data_space !== undefined && record.data_space !== identity.data_space) {
      throw new Error("session ownership mismatch: data_space");
    }
  }

  async settle(sessionId: string): Promise<void> {
    const session = this.require(sessionId);
    const scope = this.scopes.get(session.sessionId);
    if (!scope || !this.reservedSessions.delete(sessionId)) return;
    this.releaseGroupReservation(scope.group_chat_id);
  }

  async abort(sessionId: string): Promise<void> {
    const session = this.require(sessionId);
    await session.session.abort?.();
  }

  async close(sessionId: string): Promise<void> {
    const session = this.require(sessionId);
    const scope = this.scopes.get(sessionId);
    this.outputUnsubscribers.get(sessionId)?.();
    this.outputUnsubscribers.delete(sessionId);
    this.outputCaptures.delete(sessionId);
    session.session.dispose();
    this.sessions.delete(sessionId);
    this.scopes.delete(sessionId);
    if (scope && this.reservedSessions.delete(sessionId)) this.releaseGroupReservation(scope.group_chat_id);
  }

  async closeAll(): Promise<void> {
    for (const session of [...this.sessions.values()]) {
      await this.close(session.sessionId);
    }
  }

  values(): ManagedSession[] {
    return [...this.sessions.values()];
  }

  private require(sessionId: string): ManagedSession {
    const session = this.get(sessionId);
    if (!session) throw new Error(`session not found: ${sessionId}`);
    return session;
  }

  private releaseGroupReservation(groupChatId: string): void {
    const active = (this.activeByGroup.get(groupChatId) ?? 1) - 1;
    if (active > 0) this.activeByGroup.set(groupChatId, active);
    else this.activeByGroup.delete(groupChatId);
  }
}

type OutputCapture = {
  invocation: AgentInvocation;
  text: string;
};

function captureOutputEvent(capture: OutputCapture | undefined, raw: unknown): void {
  if (!capture || raw === null || typeof raw !== "object") return;
  const event = raw as Record<string, unknown>;
  const type = event.type;
  if (type === "message_update") {
    const nested = event.assistantMessageEvent;
    if (nested && typeof nested === "object" && !Array.isArray(nested)) {
      const nestedType = (nested as Record<string, unknown>).type;
      if (typeof nestedType === "string" && nestedType !== "text_delta") return;
      const delta = (nested as Record<string, unknown>).delta;
      if (typeof delta === "string") capture.text += delta;
      else {
        const content = (nested as Record<string, unknown>).content;
        if (typeof content === "string") capture.text += content;
      }
    }
    return;
  }
  if (type === "message_end") {
    const message = event.message;
    if (!message || typeof message !== "object" || Array.isArray(message)
      || (message as Record<string, unknown>).role !== "assistant") return;
    const content = extractMessageContent(event.message) ?? extractMessageContent(event.content);
    if (content !== undefined) capture.text = content;
    return;
  }
  if (type === "agent_settled") {
    const structured = parseStructuredOutput(capture.text, capture.invocation.output_contract);
    if (structured) capture.invocation.context.structured_output = structured;
  }
}

function extractMessageContent(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const content = (value as Record<string, unknown>).content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return undefined;
  return content
    .map((part) => (
      part && typeof part === "object" && typeof (part as Record<string, unknown>).text === "string"
        ? (part as Record<string, unknown>).text as string
        : ""
    ))
    .join("");
}

function parseStructuredOutput(text: string, outputContract: string): Record<string, unknown> | undefined {
  const parsed = parseJsonObject(text);
  const value = parsed && outputContract === "research_claim"
    ? normalizeResearchClaim(parsed)
    : parsed;
  const normalized = value && outputContract === "review_gate"
    ? normalizeReviewGate(value)
    : value;
  if (!value) return undefined;
  const fields: Record<string, string[]> = {
    clarification_question: ["question", "question_id"],
    claim_four_fields: ["statement", "boundary", "prediction", "falsification_condition"],
    research_claim: ["claim", "evidence_refs", "reasoning_summary", "uncertainty", "next_action"],
    review_gate: ["items"],
    postdoc_synthesis: ["summary", "recommendations", "limitations", "open_questions"],
  };
  const required = fields[outputContract];
  if (!required || required.some((field) => !(field in normalized!))) return undefined;
  return normalized;
}

const reviewKinds = [
  "counterexample",
  "falsification_condition",
  "missing_observation",
] as const;

function normalizeReviewGate(value: Record<string, unknown>): Record<string, unknown> {
  if (Array.isArray(value.items)) return value;
  const items: Record<string, unknown>[] = [];
  for (const kind of reviewKinds) {
    let category = value[kind];
    if (category && typeof category === "object" && !Array.isArray(category)) {
      category = (category as Record<string, unknown>).items;
    }
    if (typeof category === "string") category = [category];
    if (!Array.isArray(category)) return value;
    for (const raw of category) {
      if (typeof raw === "string") {
        items.push({ kind, content: raw });
        continue;
      }
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
      const item = { ...(raw as Record<string, unknown>) };
      const content = ["content", "description", "statement", "finding"]
        .map((field) => item[field])
        .find((field): field is string => typeof field === "string");
      if (content) {
        item.kind = typeof item.kind === "string" ? item.kind : kind;
        item.content = content;
        items.push(item);
      }
    }
  }
  return items.length > 0 ? { ...value, items } : value;
}

function normalizeResearchClaim(value: Record<string, unknown>): Record<string, unknown> {
  const claim = value.claim;
  if (!claim || typeof claim !== "object" || Array.isArray(claim)) return value;
  const nested = claim as Record<string, unknown>;
  const sections = [
    ["判断", nested.judgment],
    ["适用边界", nested.boundary ?? nested.applicable_boundary],
    ["可观察预测", nested.prediction ?? nested.observable_prediction],
    ["可推翻条件", nested.falsification_condition ?? nested.falsification],
  ] as const;
  const rendered = sections.map(([label, content]) => {
    const text = renderClaimSection(content);
    return text ? `${label}：${text}` : "";
  });
  if (rendered.some((section) => !section)) return value;
  return {
    ...value,
    claim: rendered.join("\n"),
  };
}

function renderClaimSection(value: unknown): string | undefined {
  if (typeof value === "string") return value.trim() || undefined;
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const lines = Object.entries(value)
    .flatMap(([key, nested]) => (
      typeof nested === "string" && nested.trim() ? `${key}：${nested.trim()}` : []
    ));
  return lines.length > 0 ? lines.join("\n") : undefined;
}

function parseJsonObject(text: string): Record<string, unknown> | undefined {
  const candidates = [text.trim()];
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1]?.trim();
  if (fenced) candidates.push(fenced);
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) candidates.push(text.slice(start, end + 1));
  for (const candidate of candidates) {
    const variants = [candidate];
    const decoded = decodeEscapedJsonCandidate(candidate);
    if (decoded) variants.push(decoded);
    for (const variant of variants) {
      try {
        const value: unknown = JSON.parse(variant);
        if (value && typeof value === "object" && !Array.isArray(value)) {
          return value as Record<string, unknown>;
        }
      } catch {
        // The API result validator will reject an unparseable model response.
      }
    }
  }
  return undefined;
}

function decodeEscapedJsonCandidate(candidate: string): string | undefined {
  const trimmed = candidate.trim();
  if (!trimmed.includes("\\n") && !trimmed.includes('\\"')) return undefined;
  try {
    const decoded: unknown = JSON.parse(`"${trimmed}"`);
    if (typeof decoded !== "string") return undefined;
    return decoded.trim().replace(/^json\s*/i, "");
  } catch {
    return undefined;
  }
}

export function validateInvocationRoleBoundary(invocation: AgentInvocation): void {
  if (invocation.phase === "task_clarification") {
    if (!["master_student", "phd_student", "postdoc"].includes(invocation.role)) {
      throw new Error("task_clarification native session requires a research member role");
    }
    return;
  }
  if (invocation.role === "phd_student" && invocation.phase !== "review_gate") {
    throw new Error("phd_student native session is limited to review_gate");
  }
  if (invocation.role === "postdoc") {
    if (invocation.phase !== "postdoc_exchange") {
      throw new Error("postdoc native session is limited to postdoc_exchange");
    }
    const profile = invocation.context.agent_profile;
    const profileDomain = profile && typeof profile === "object" && !Array.isArray(profile)
      ? (profile as Record<string, unknown>).specialty_domain
      : undefined;
    if (typeof invocation.context.specialty_domain !== "string" && typeof profileDomain !== "string") {
      throw new Error("postdoc native session requires specialty_domain");
    }
  }
  if (invocation.role === "master_student" && !["independent_analysis", "revision"].includes(invocation.phase)) {
    throw new Error("master_student native session is limited to independent_analysis or revision");
  }
}

function scopeKey(scope: ScopeIdentity | AgentInvocation): string {
  return JSON.stringify([
    scope.group_chat_id,
    scope.run_id,
    scope.agent_id,
    scope.data_space || "",
    "invocation_id" in scope ? scope.invocation_id || "" : "",
    scope.task_id || "",
    [...(scope.document_scope ?? [])].sort(),
  ]);
}

function persistentInvocationOptions(
  invocation: AgentInvocation,
  options: RegistryOptions,
): SessionFactoryOptions {
  if (options.storage !== "persistent") {
    return { ...options, sdk: options.sdk };
  }
  const baseConfig = options.config ?? loadConfig();
  const segment = safeInvocationSegment(invocation.invocation_id);
  const taskSegment = safeInvocationSegment(invocation.task_id || "synthetic");
  const documentSegment = documentScopeSegment(invocation.document_scope ?? []);
  const root = join(
    baseConfig.sessionRoot,
    "tasks",
    taskSegment,
    "documents",
    documentSegment,
    "invocations",
    segment,
  );
  return {
    ...options,
    sdk: options.sdk,
    config: {
      ...baseConfig,
      sessionRoot: root,
      runtimeCwd: join(root, "runtime-cwd"),
      agentDir: join(root, "agent"),
    },
  };
}

function safeInvocationSegment(value: string): string {
  const normalized = value.trim();
  if (!normalized || normalized === "." || normalized === ".." || /[\\/:*?"<>|]/.test(normalized)) {
    throw new Error("invocation_id contains an unsafe path segment");
  }
  return normalized;
}

function sameDocumentScope(left: string[] | undefined, right: string[] | undefined): boolean {
  return JSON.stringify([...(left ?? [])].sort()) === JSON.stringify([...(right ?? [])].sort());
}

function documentScopeSegment(scope: string[]): string {
  const normalized = JSON.stringify([...scope].sort());
  return `scope-${createHash("sha256").update(normalized).digest("hex").slice(0, 16)}`;
}

export type { ToolFactory };
