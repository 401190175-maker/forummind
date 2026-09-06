export const runtimeEventTypes = [
  "agent_started",
  "text_delta",
  "text_completed",
  "tool_started",
  "tool_update",
  "tool_completed",
  "turn_started",
  "turn_completed",
  "agent_settled",
  "agent_failed",
  "agent_aborted",
] as const;

export type RuntimeEventType = (typeof runtimeEventTypes)[number];

export type AgentInvocation = {
  invocation_id: string;
  run_id: string;
  group_chat_id: string;
  cycle: number | null;
  phase: string;
  agent_id: string;
  role: string;
  profile_version: string;
  agent_instruction: string;
  task: string;
  input_refs: string[];
  context: Record<string, unknown>;
  allowed_tools: string[];
  output_contract: string;
  data_space: string;
  safety_rules: string[];
  task_id?: string;
  document_scope?: string[];
};

export type AgentResult = {
  agent_id: string;
  status: "ok" | "fallback" | "error";
  content: string;
  structured_output: Record<string, unknown>;
  tool_calls: Record<string, unknown>[];
  runtime_state_ref: string;
  warnings: string[];
  error: string;
  error_code: string;
  data_space: string;
};

export type RuntimeEvent = {
  event_id: string;
  cursor: number;
  session_id: string;
  invocation_id: string;
  run_id: string;
  group_chat_id: string;
  agent_id: string;
  phase: string;
  type: RuntimeEventType;
  payload: Record<string, unknown>;
  data_space: string;
  timestamp: number;
  task_id?: string;
  document_scope?: string[];
};

export type SessionRecord = {
  session_id: string;
  session_scope: string;
  group_chat_id: string;
  run_id: string;
  agent_id: string;
  phase: string;
  data_space: string;
  cursor: number;
  status: "active" | "paused" | "settled" | "aborted" | "failed" | "closed";
  persisted: boolean;
};

export type RuntimeControl = {
  action: "pause" | "resume" | "abort" | "retry" | "steer" | "follow-up";
  message?: string;
};

export type RuntimeError = {
  code: string;
  message: string;
  retryable: boolean;
};

type ObjectRecord = Record<string, unknown>;

function asObject(input: unknown, label: string): ObjectRecord {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    throw new Error(`${label} must be an object`);
  }
  return input as ObjectRecord;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

function stringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${field} must be an array of strings`);
  }
  return [...value];
}

function record(value: unknown, field: string): Record<string, unknown> {
  return asObject(value, field);
}

function instructionText(value: unknown): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const serialized = JSON.stringify(value);
    if (serialized && serialized !== "{}") return serialized;
  }
  throw new Error("agent_instruction must be a non-empty string or object");
}

export function parseInvocation(input: unknown): AgentInvocation {
  const value = asObject(input, "invocation");
  const cycle = value.cycle;
  if (cycle !== null && (!Number.isInteger(cycle) || (cycle as number) < 0)) {
    throw new Error("cycle must be null or a non-negative integer");
  }
  const dataSpace = requiredString(value.data_space, "data_space");
  const taskId = value.task_id === undefined ? "" : requiredString(value.task_id, "task_id");
  const documentScope = value.document_scope === undefined ? [] : stringArray(value.document_scope, "document_scope");
  if (dataSpace !== "synthetic" && !taskId) throw new Error("task_id is required for real data");
  return {
    invocation_id: requiredString(value.invocation_id, "invocation_id"),
    run_id: requiredString(value.run_id, "run_id"),
    group_chat_id: requiredString(value.group_chat_id, "group_chat_id"),
    cycle: cycle as number | null,
    phase: requiredString(value.phase, "phase"),
    agent_id: requiredString(value.agent_id, "agent_id"),
    role: requiredString(value.role, "role"),
    profile_version: requiredString(value.profile_version, "profile_version"),
    agent_instruction: instructionText(value.agent_instruction),
    task: requiredString(value.task, "task"),
    input_refs: stringArray(value.input_refs, "input_refs"),
    context: record(value.context, "context"),
    allowed_tools: stringArray(value.allowed_tools, "allowed_tools"),
    output_contract: requiredString(value.output_contract, "output_contract"),
    data_space: dataSpace,
    safety_rules: stringArray(value.safety_rules, "safety_rules"),
    task_id: taskId,
    document_scope: documentScope,
  };
}

export function parseRuntimeEvent(input: unknown): RuntimeEvent {
  const value = asObject(input, "runtime event");
  if (!Number.isInteger(value.cursor) || (value.cursor as number) < 1) {
    throw new Error("runtime event cursor is invalid");
  }
  if (typeof value.timestamp !== "number" || !Number.isFinite(value.timestamp)) {
    throw new Error("runtime event timestamp is invalid");
  }
  const type = requiredString(value.type, "type");
  if (!(runtimeEventTypes as readonly string[]).includes(type)) {
    throw new Error(`runtime event type is invalid: ${type}`);
  }
  const dataSpace = requiredString(value.data_space, "data_space");
  const taskId = value.task_id === undefined ? "" : requiredString(value.task_id, "task_id");
  const documentScope = value.document_scope === undefined ? [] : stringArray(value.document_scope, "document_scope");
  if (dataSpace !== "synthetic" && !taskId) throw new Error("runtime event task_id is required for real data");
  return {
    event_id: requiredString(value.event_id, "event_id"),
    cursor: value.cursor as number,
    session_id: requiredString(value.session_id, "session_id"),
    invocation_id: requiredString(value.invocation_id, "invocation_id"),
    run_id: requiredString(value.run_id, "run_id"),
    group_chat_id: requiredString(value.group_chat_id, "group_chat_id"),
    agent_id: requiredString(value.agent_id, "agent_id"),
    phase: requiredString(value.phase, "phase"),
    type: type as RuntimeEventType,
    payload: record(value.payload, "runtime event payload"),
    data_space: dataSpace,
    timestamp: value.timestamp as number,
    task_id: taskId,
    document_scope: documentScope,
  };
}
