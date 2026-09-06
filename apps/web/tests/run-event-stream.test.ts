import assert from "node:assert/strict";
import { test } from "node:test";

import { parseSseText } from "../lib/run-event-stream";
import type { RuntimeEvent } from "../lib/api";
import { reduceRuntimeEvent, type RunStoreState } from "../lib/stores/run-store";

function state(): RunStoreState {
  return {
    runId: "run-1",
    runGroupChatId: "group-1",
    snapshot: null,
    meetingEvents: [],
    visibleSteps: 0,
    polling: "running",
    error: null,
    agentStates: {},
    candidateByAgent: {},
    eventCursor: 0,
    connectionState: "connected",
    processedEventIds: {},
    runtimeEvents: [],
    start: async () => undefined,
    startLive: async () => undefined,
    startClarificationLive: async () => undefined,
    refresh: async () => undefined,
    resume: async () => undefined,
    stop: () => undefined,
    pause: () => undefined,
    reset: () => undefined,
    control: async () => undefined,
  };
}

function delta(eventId: string, cursor: number, content_delta: string): RuntimeEvent {
  return {
    event_id: eventId,
    cursor,
    run_id: "run-1",
    agent_id: "a-1",
    type: "text_delta",
    payload: { content_delta },
  };
}

test("SSE frames expose runtime event identity and cursor", () => {
  const events = parseSseText([
    "id: 41",
    "event: runtime.text_delta",
    'data: {"run_id":"run-1","agent_id":"a-1","payload":{"content_delta":"A"}}',
    "",
    "",
  ].join("\n"));

  assert.equal(events.length, 1);
  assert.equal(events[0].cursor, 41);
  assert.equal(events[0].type, "text_delta");
});

test("runtime event reduction resumes from the last cursor without duplicating deltas", () => {
  let current = state();
  current = { ...current, ...reduceRuntimeEvent(current, delta("event-41", 41, "A")) };
  current = { ...current, ...reduceRuntimeEvent(current, delta("event-42", 42, "B")) };
  const duplicate = reduceRuntimeEvent(current, delta("event-42", 42, "B"));

  assert.equal(current.candidateByAgent["a-1"], "AB");
  assert.equal(current.eventCursor, 42);
  assert.deepEqual(duplicate, {});
});
