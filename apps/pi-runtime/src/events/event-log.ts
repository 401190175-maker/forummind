import { randomUUID } from "node:crypto";
import type { AgentInvocation, RuntimeEvent, RuntimeEventType } from "../contracts.js";

export type RuntimeEventDraft = Omit<RuntimeEvent, "event_id" | "cursor" | "timestamp"> & {
  type: RuntimeEventType;
};

export type RuntimeEventListener = (event: RuntimeEvent) => void;

export class RuntimeEventLog {
  private readonly events: RuntimeEvent[] = [];
  private readonly listeners = new Set<RuntimeEventListener>();
  private nextCursor = 1;
  private settledInvocations = new Set<string>();

  constructor(private readonly maxEvents = 256) {}

  append(draft: RuntimeEventDraft): RuntimeEvent | null {
    if (draft.type === "agent_started" && this.events.some(
      (event) => event.invocation_id === draft.invocation_id && event.type === "agent_started",
    )) return null;
    if (["agent_settled", "agent_failed", "agent_aborted"].includes(draft.type)) {
      if (this.settledInvocations.has(draft.invocation_id)) return null;
      this.settledInvocations.add(draft.invocation_id);
    }
    const event: RuntimeEvent = {
      ...draft,
      event_id: randomUUID(),
      cursor: this.nextCursor++,
      timestamp: Date.now() / 1000,
    };
    this.events.push(event);
    while (this.events.length > this.maxEvents) this.events.shift();
    for (const listener of this.listeners) listener(event);
    return event;
  }

  list(after = 0): RuntimeEvent[] {
    return this.events.filter((event) => event.cursor > after).map((event) => ({
      ...event,
      payload: { ...event.payload },
    }));
  }

  latestCursor(): number {
    return this.nextCursor - 1;
  }

  hasSettled(invocationId: string): boolean {
    return this.settledInvocations.has(invocationId);
  }

  subscribe(listener: RuntimeEventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export function identityDraft(
  invocation: AgentInvocation,
  sessionId: string,
  type: RuntimeEventType,
  payload: Record<string, unknown> = {},
): RuntimeEventDraft {
  return {
    session_id: sessionId,
    invocation_id: invocation.invocation_id,
    run_id: invocation.run_id,
    group_chat_id: invocation.group_chat_id,
    agent_id: invocation.agent_id,
    phase: invocation.phase,
    type,
    payload,
    data_space: invocation.data_space,
    task_id: invocation.task_id ?? "",
    document_scope: [...(invocation.document_scope ?? [])],
  };
}
