import { createHash } from "node:crypto";
import type { AgentInvocation, RuntimeEventType } from "../contracts.js";
import { identityDraft, type RuntimeEventDraft } from "./event-log.js";

export function adaptPiEvent(
  raw: unknown,
  invocation: AgentInvocation,
  sessionId: string,
): RuntimeEventDraft | null {
  if (raw === null || typeof raw !== "object") return null;
  const event = raw as Record<string, unknown>;
  const type = event.type;
  if (typeof type !== "string") return null;
  const failure = extractAssistantFailure(event);
  const mapped = failure ? "agent_failed" : mapType(type, event);
  if (!mapped) return null;
  let payload: Record<string, unknown> = {};
  if (mapped === "agent_failed") {
    payload = failure!;
  } else if (mapped === "text_delta") {
    const delta = extractTextDelta(event);
    if (!delta) return null;
    payload = { content_delta: delta };
  } else if (mapped === "text_completed") {
    const content = extractMessageText(event);
    if (content) payload = { content };
  } else if (mapped === "tool_started" || mapped === "tool_update" || mapped === "tool_completed") {
    payload = summarizeToolEvent(event, mapped);
  }
  return identityDraft(invocation, sessionId, mapped, payload);
}

function extractAssistantFailure(event: Record<string, unknown>): Record<string, string> | undefined {
  if (event.type !== "message_end") return undefined;
  const message = event.message;
  if (!message || typeof message !== "object" || Array.isArray(message)) return undefined;
  const value = message as Record<string, unknown>;
  if (value.role !== "assistant") return undefined;
  const stopReason = value.stopReason ?? value.stop_reason;
  const rawError = value.errorMessage ?? value.error_message ?? event.errorMessage ?? event.error_message;
  if (stopReason !== "error" && !(typeof rawError === "string" && rawError.trim())) return undefined;
  const error = typeof rawError === "string" && rawError.trim()
    ? rawError.trim()
    : "model provider request failed";
  return { error, error_code: providerErrorCode(error) };
}

function providerErrorCode(error: string): string {
  const normalized = error.toLowerCase();
  if (/invalid[ _-]?api[ _-]?key|\b401\b|\b403\b|unauthori[sz]ed|forbidden/.test(normalized)) {
    return "pi_auth";
  }
  if (/timeout|timed out|aborterror/.test(normalized)) return "pi_timeout";
  if (/connection error|econn|network|fetch failed|dns|unavailable/.test(normalized)) {
    return "pi_unavailable";
  }
  return "pi_runtime";
}

function mapType(type: string, event: Record<string, unknown>): RuntimeEventType | null {
  const mapping: Record<string, RuntimeEventType> = {
    agent_start: "agent_started",
    agent_settled: "agent_settled",
    turn_start: "turn_started",
    turn_end: "turn_completed",
    tool_execution_start: "tool_started",
    tool_execution_update: "tool_update",
    tool_execution_end: "tool_completed",
  };
  if (mapping[type]) return mapping[type];
  if (type === "message_update") {
    const nested = event.assistantMessageEvent;
    if (
      nested &&
      typeof nested === "object" &&
      !Array.isArray(nested) &&
      typeof (nested as Record<string, unknown>).type === "string" &&
      (nested as Record<string, unknown>).type !== "text_delta"
    ) return null;
    return "text_delta";
  }
  if (type === "message_end") {
    const message = event.message;
    if (!message || typeof message !== "object" || Array.isArray(message)) return null;
    return (message as Record<string, unknown>).role === "assistant" ? "text_completed" : null;
  }
  return null;
}

function extractTextDelta(event: Record<string, unknown>): string {
  const candidates = [
    event.delta,
    event.content_delta,
    (event.assistantMessageEvent as Record<string, unknown> | undefined)?.delta,
    (event.assistantMessageEvent as Record<string, unknown> | undefined)?.content,
  ];
  return candidates.find((value): value is string => typeof value === "string") ?? "";
}

function extractMessageText(event: Record<string, unknown>): string {
  const message = event.message as Record<string, unknown> | undefined;
  const content = message?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => (part && typeof part === "object" && typeof (part as Record<string, unknown>).text === "string" ? (part as Record<string, unknown>).text : ""))
      .join("");
  }
  return typeof event.content === "string" ? event.content : "";
}

function summarizeToolEvent(event: Record<string, unknown>, type: RuntimeEventType): Record<string, unknown> {
  const args = event.args;
  const serialized = JSON.stringify(args ?? {});
  return {
    tool_name: typeof event.toolName === "string" ? event.toolName : "unknown",
    tool_call_id: typeof event.toolCallId === "string" ? event.toolCallId : "",
    argument_keys: args && typeof args === "object" && !Array.isArray(args) ? Object.keys(args) : [],
    argument_sha256: createHash("sha256").update(serialized).digest("hex"),
    is_error: type === "tool_completed" ? Boolean(event.isError) : false,
  };
}
