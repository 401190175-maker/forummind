import { apiBaseUrl, type RuntimeEvent } from "./api";

export type RunEventConnectionState = "connected" | "reconnecting" | "closed";

export type RunEventCallbacks = {
  onEvent: (event: RuntimeEvent) => void;
  onState: (state: RunEventConnectionState) => void;
};

export function parseSseText(text: string): RuntimeEvent[] {
  const events: RuntimeEvent[] = [];
  for (const block of text.split(/\r?\n\r?\n/)) {
    if (!block.trim()) continue;
    let id = "";
    let eventName = "runtime.event";
    const data: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("id:")) id = line.slice(3).trim();
      else if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!id || data.length === 0) continue;
    try {
      const payload = JSON.parse(data.join("\n")) as RuntimeEvent;
      const cursor = Number.isInteger(payload.cursor) ? payload.cursor : Number(id);
      if (!Number.isInteger(cursor) || cursor < 0) continue;
      events.push({
        ...payload,
        event_id: payload.event_id || id,
        cursor,
        type: payload.type || eventName.replace(/^runtime\./, ""),
      });
    } catch {
      // Ignore malformed frames; the next reconnect replays from the last cursor.
    }
  }
  return events;
}

export function connectRunEvents(
  runId: string,
  after: number,
  callbacks: RunEventCallbacks,
): AbortController {
  const controller = new AbortController();
  const connect = async () => {
    callbacks.onState("reconnecting");
    try {
      const response = await fetch(`${apiBaseUrl()}/runs/${encodeURIComponent(runId)}/events?after=${after}`, {
        headers: { Accept: "text/event-stream" },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error(`SSE HTTP ${response.status}`);
      callbacks.onState("connected");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      while (!controller.signal.aborted) {
        const next = await reader.read();
        pending += decoder.decode(next.value ?? new Uint8Array(), { stream: !next.done });
        const split = pending.split(/\r?\n\r?\n/);
        pending = split.pop() ?? "";
        for (const event of parseSseText(split.join("\n\n"))) callbacks.onEvent(event);
        if (next.done) break;
      }
      if (pending.trim()) {
        for (const event of parseSseText(`${pending}\n\n`)) callbacks.onEvent(event);
      }
      if (!controller.signal.aborted) callbacks.onState("closed");
    } catch {
      if (!controller.signal.aborted) callbacks.onState("reconnecting");
    }
  };
  void connect();
  return controller;
}
