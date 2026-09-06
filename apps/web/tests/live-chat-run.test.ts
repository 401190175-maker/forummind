import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import { startClarificationLiveRun } from "../lib/api";
import {
  reduceRuntimeEvent,
  toChatRunEvent,
  useRunStore,
  type RunStoreState,
} from "../lib/stores/run-store";
import type { RuntimeEvent } from "../lib/api";

process.env.NEXT_PUBLIC_API_BASE_URL = "http://test.local";

type CapturedRequest = { path: string; body: unknown };

const requests: CapturedRequest[] = [];
const realFetch = globalThis.fetch;

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

function event(
  partial: Partial<RuntimeEvent> & { event_id: string; cursor: number; type: string },
): RuntimeEvent {
  return {
    run_id: "run-1",
    agent_id: "a-1",
    payload: {},
    ...partial,
  };
}

beforeEach(() => {
  requests.length = 0;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requests.push({
      path: String(input).replace("http://test.local", ""),
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    });
    return new Response(JSON.stringify({ run_id: "run-1", status: "running" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = realFetch;
  useRunStore.getState().reset();
});

test("clarified run API always posts live mode", async () => {
  await startClarificationLiveRun("gc-1", "clarification-1");
  assert.deepEqual(requests[0], {
    path: "/group-chats/gc-1/runs",
    body: { mode: "live", clarification_id: "clarification-1" },
  });
});

test("clarified run launch exposes an actionable API failure to its caller", async () => {
  globalThis.fetch = (async () => new Response(
    JSON.stringify({ detail: "研究服务暂时不可用，尚未开始分析。" }),
    { status: 409, headers: { "Content-Type": "application/json" } },
  )) as typeof fetch;

  await assert.rejects(
    () => useRunStore.getState().startClarificationLive("gc-1", "clarification-1"),
    /研究服务暂时不可用，尚未开始分析。/,
  );
  assert.equal(useRunStore.getState().polling, "idle");
  assert.equal(useRunStore.getState().error, "研究服务暂时不可用，尚未开始分析。");
});

test("a duplicate SSE event creates no duplicate chat event", () => {
  const delta = event({ event_id: "event-1", cursor: 1, type: "tool_started" });
  const first = reduceRuntimeEvent(state(), delta);
  const duplicate = reduceRuntimeEvent({ ...state(), ...first }, delta);
  assert.deepEqual(duplicate, {});
});

test("a virtual SSE settled marker cannot advance the resume cursor", () => {
  const first = reduceRuntimeEvent(
    state(),
    event({ event_id: "event-1", cursor: 1, type: "tool_started" }),
  );
  const afterFirst = { ...state(), ...first };
  const virtualSettled = reduceRuntimeEvent(
    afterFirst,
    event({ event_id: "run-settled:run-1:2", cursor: 2, type: "settled" }),
  );

  assert.deepEqual(virtualSettled, {});

  const laterPersistedEvent = reduceRuntimeEvent(
    { ...afterFirst, ...virtualSettled },
    event({ event_id: "event-2", cursor: 2, type: "agent_settled" }),
  );
  assert.equal(laterPersistedEvent.eventCursor, 2);
});

test("run events project to safe chat progress candidates", () => {
  assert.equal(
    toChatRunEvent(event({ event_id: "e1", cursor: 1, type: "agent_started" }))?.content,
    "正在检索课题组资料",
  );
  assert.equal(
    toChatRunEvent(event({ event_id: "e2", cursor: 2, type: "tool_started" }))?.content,
    "正在整理候选结论",
  );
  assert.equal(
    toChatRunEvent(event({ event_id: "e3", cursor: 3, type: "agent_settled" }))?.kind,
    "candidate",
  );
  assert.equal(
    toChatRunEvent(event({ event_id: "e4", cursor: 4, type: "text_delta" })),
    null,
  );
});
