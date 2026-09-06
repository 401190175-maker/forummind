"use client";

import { create } from "zustand";
import {
  controlRun,
  getMeetingEvents,
  getRun,
  startClarificationLiveRun,
  startLiveRun,
  startRun,
  type MeetingEvent,
  type RunMode,
  type RunSnapshot,
} from "@/lib/api";
import type { RuntimeEvent } from "@/lib/api";
import { connectRunEvents, type RunEventConnectionState } from "@/lib/run-event-stream";
import type { ChatTimelineItem } from "@/components/group-chat/chat-types";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import {
  clearPersistedRunId,
  readPersistedRunId,
  readPersistedRunCursor,
  savePersistedRunId,
  savePersistedRunCursor,
  type RunStorage,
} from "./run-recovery";

/** 轮询间隔（design.md §4.1）。 */
export const POLL_INTERVAL_MS = 1000;
/** replay 渐进渲染间隔。 */
export const REVEAL_INTERVAL_MS = 400;

const TERMINAL_RUN_STATUSES = new Set([
  "completed",
  "conclusion",
  "terminated",
  "cycle_exhausted",
  "failed",
]);

export type RunPollingStatus =
  | "idle"
  | "starting"
  | "running"
  | "stopped"
  | "failed"
  | "error";

export type AgentRuntimeState = "idle" | "analyzing" | "tool" | "reviewing" | "completed" | "aborted" | "failed";

export type RunStoreState = {
  runId: string | null;
  runGroupChatId: string | null;
  snapshot: RunSnapshot | null;
  meetingEvents: MeetingEvent[];
  /** replay 渐进渲染进度：已可见步骤数（上限 = snapshot.steps.length）。 */
  visibleSteps: number;
  polling: RunPollingStatus;
  error: string | null;
  agentStates: Record<string, AgentRuntimeState>;
  candidateByAgent: Record<string, string>;
  eventCursor: number;
  connectionState: RunEventConnectionState;
  processedEventIds: Record<string, true>;
  runtimeEvents: RuntimeEvent[];
  /** 启动 run 并开始轮询：startRun → 存 runId → polling=running → 两个定时器。 */
  start: (groupChatId: string, mode: RunMode, clarificationId?: string) => Promise<void>;
  /** 用研究任务和指定 Agent 启动真实 Live Run。 */
  startLive: (groupChatId: string, taskId: string, agentId: string) => Promise<void>;
  /** 从已确认的澄清启动真实 Live Run（浏览器唯一运行入口）。 */
  startClarificationLive: (groupChatId: string, clarificationId: string) => Promise<void>;
  /** 单次 getRun 拉取并更新快照；服务端终态到达后停表。 */
  refresh: () => Promise<void>;
  /** 仅用本地保存的 run_id 从服务端恢复 Run 快照与正式组会事件。 */
  resume: (groupChatId?: string) => Promise<void>;
  /** 停止轮询（页面卸载 / 终止 / 错误后）。 */
  stop: () => void;
  /** 暂停轮询并回到空闲态，但保留当前快照作为 demo 进度。 */
  pause: () => void;
  /** 重置为初始态。 */
  reset: () => void;
  control: (action: "pause" | "resume" | "abort" | "retry", message?: string) => Promise<void>;
};

/* 模块级私有定时器（design.md §4.2）。 */
let pollTimer: ReturnType<typeof setInterval> | null = null;
let revealTimer: ReturnType<typeof setInterval> | null = null;
let latestRefreshId = 0;
let eventController: AbortController | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

function clearTimers() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (revealTimer !== null) {
    clearInterval(revealTimer);
    revealTimer = null;
  }
}

function closeEventStream() {
  eventController?.abort();
  eventController = null;
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

export function reduceRuntimeEvent(state: RunStoreState, event: RuntimeEvent): Partial<RunStoreState> {
  if (event.type === "settled") return {};
  if (event.cursor <= state.eventCursor || state.processedEventIds[event.event_id]) return {};
  const processedEventIds: Record<string, true> = {
    ...state.processedEventIds,
    [event.event_id]: true,
  };
  const runtimeEvents = [...state.runtimeEvents, event].slice(-256);
  const agentId = event.agent_id;
  const agentStates = { ...state.agentStates };
  const candidateByAgent = { ...state.candidateByAgent };
  if (agentId) {
    if (event.type === "agent_started" || event.type === "turn_started") agentStates[agentId] = "analyzing";
    if (event.type === "tool_started" || event.type === "tool_update") agentStates[agentId] = "tool";
    if (event.type === "tool_completed") agentStates[agentId] = "analyzing";
    if (event.type === "agent_settled") agentStates[agentId] = "completed";
    if (event.type === "agent_failed") agentStates[agentId] = "failed";
    if (event.type === "agent_aborted") agentStates[agentId] = "aborted";
    if (event.type === "text_delta") {
      const delta = event.payload.content_delta;
      if (typeof delta === "string") candidateByAgent[agentId] = (candidateByAgent[agentId] ?? "") + delta;
    }
  }
  return { eventCursor: event.cursor, processedEventIds, runtimeEvents, agentStates, candidateByAgent };
}

function runEventLabel(event: RuntimeEvent): string | null {
  switch (event.type) {
    case "agent_started":
    case "turn_started":
    case "run_started":
      return "正在检索课题组资料";
    case "tool_started":
    case "tool_update":
    case "tool_completed":
      return "正在整理候选结论";
    case "agent_settled":
    case "run_completed":
    case "conclusion":
      return "已生成候选结果，等待你审阅";
    case "agent_failed":
    case "run_failed":
      return "分析未能完成，请检查资料和成员配置后重试";
    default:
      return null;
  }
}

/** 把一条去重后的运行时事件投影为安全的聊天时间轴项（进度候选）。 */
export function toChatRunEvent(event: RuntimeEvent): ChatTimelineItem | null {
  const content = runEventLabel(event);
  if (content === null) return null;
  const terminal =
    event.type === "agent_settled" ||
    event.type === "run_completed" ||
    event.type === "conclusion";
  return {
    id: `run-event-${event.event_id}`,
    side: "left",
    senderName: "博士后",
    kind: terminal ? "candidate" : "run_status",
    content,
    payload: { run_id: event.run_id, event_id: event.event_id },
    createdAt: event.timestamp ?? 0,
  };
}

export function consumeTextDelta(event: RuntimeEvent): RunStoreState {
  const base = useRunStore.getState();
  useRunStore.setState(reduceRuntimeEvent(base, event));
  return useRunStore.getState();
}

function openEventStream(
  runId: string,
  get: () => RunStoreState,
  set: (partial: Partial<RunStoreState> | ((state: RunStoreState) => Partial<RunStoreState>)) => void,
) {
  closeEventStream();
  eventController = connectRunEvents(runId, get().eventCursor, {
  onEvent: (event) => set((state) => {
      const update = reduceRuntimeEvent(state, event);
      if (update.eventCursor !== undefined && state.runGroupChatId) {
        const storage = browserStorage();
        if (storage) savePersistedRunCursor(state.runGroupChatId, runId, update.eventCursor, storage);
      }
      return update;
    }),
    onState: (connectionState) => {
      set({ connectionState });
      if (connectionState === "reconnecting" && get().runId === runId && reconnectTimer === null) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          if (get().runId === runId) openEventStream(runId, get, set);
        }, 500);
      }
    },
  });
}

function browserStorage(): RunStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function startTimers(
  get: () => RunStoreState,
  set: (partial: Partial<RunStoreState>) => void,
) {
  clearTimers();
  pollTimer = setInterval(() => void get().refresh(), POLL_INTERVAL_MS);
  revealTimer = setInterval(() => {
    const { snapshot, visibleSteps } = get();
    const max = snapshot?.steps.length ?? 0;
    if (visibleSteps < max) {
      set({ visibleSteps: visibleSteps + 1 });
    }
  }, REVEAL_INTERVAL_MS);
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError || err instanceof ApiConfigError) {
    return err.message;
  }
  return "运行出错，请重试";
}

export const useRunStore = create<RunStoreState>((set, get) => ({
  runId: null,
  runGroupChatId: null,
  snapshot: null,
  meetingEvents: [],
  visibleSteps: 0,
  polling: "idle",
  error: null,
  agentStates: {},
  candidateByAgent: {},
  eventCursor: 0,
  connectionState: "closed",
  processedEventIds: {},
  runtimeEvents: [],

  start: async (groupChatId, mode, clarificationId) => {
    latestRefreshId += 1;
    clearTimers();
    set({ polling: "starting", error: null });
    try {
      const res = await startRun(groupChatId, mode, clarificationId);
      const storage = browserStorage();
      if (storage) {
        savePersistedRunId(groupChatId, res.run_id, storage);
        savePersistedRunCursor(groupChatId, res.run_id, 0, storage);
      }
      set({
        runId: res.run_id,
        runGroupChatId: groupChatId,
        snapshot: null,
        meetingEvents: [],
        visibleSteps: 0,
        polling: "running",
        agentStates: {},
        candidateByAgent: {},
        eventCursor: 0,
        connectionState: "closed",
        processedEventIds: {},
        runtimeEvents: [],
      });
      await get().refresh();
      openEventStream(res.run_id, get, set);
      if (get().polling === "running") {
        startTimers(get, set);
      }
    } catch (err) {
      clearTimers();
      set({ polling: "idle", error: errorMessage(err) });
      throw err;
    }
  },

  startLive: async (groupChatId, taskId, agentId) => {
    latestRefreshId += 1;
    clearTimers();
    set({ polling: "starting", error: null });
    try {
      const res = await startLiveRun(groupChatId, taskId, agentId);
      const storage = browserStorage();
      if (storage) {
        savePersistedRunId(groupChatId, res.run_id, storage);
        savePersistedRunCursor(groupChatId, res.run_id, 0, storage);
      }
      set({
        runId: res.run_id,
        runGroupChatId: groupChatId,
        snapshot: null,
        meetingEvents: [],
        visibleSteps: 0,
        polling: "running",
        agentStates: {},
        candidateByAgent: {},
        eventCursor: 0,
        connectionState: "closed",
        processedEventIds: {},
        runtimeEvents: [],
      });
      await get().refresh();
      openEventStream(res.run_id, get, set);
      if (get().polling === "running") startTimers(get, set);
    } catch (err) {
      clearTimers();
      set({ polling: "idle", error: errorMessage(err) });
      throw err;
    }
  },

  startClarificationLive: async (groupChatId, clarificationId) => {
    latestRefreshId += 1;
    clearTimers();
    set({ polling: "starting", error: null });
    try {
      const res = await startClarificationLiveRun(groupChatId, clarificationId);
      const storage = browserStorage();
      if (storage) {
        savePersistedRunId(groupChatId, res.run_id, storage);
        savePersistedRunCursor(groupChatId, res.run_id, 0, storage);
      }
      set({
        runId: res.run_id,
        runGroupChatId: groupChatId,
        snapshot: null,
        meetingEvents: [],
        visibleSteps: 0,
        polling: "running",
        agentStates: {},
        candidateByAgent: {},
        eventCursor: 0,
        connectionState: "closed",
        processedEventIds: {},
        runtimeEvents: [],
      });
      await get().refresh();
      openEventStream(res.run_id, get, set);
      if (get().polling === "running") startTimers(get, set);
    } catch (err) {
      clearTimers();
      set({ polling: "idle", error: errorMessage(err) });
      throw err;
    }
  },

  refresh: async () => {
    const { runId } = get();
    if (!runId) return;
    const refreshId = ++latestRefreshId;
    try {
      const [snapshot, meetingEvents] = await Promise.all([
        getRun(runId),
        getMeetingEvents(runId),
      ]);
      if (refreshId !== latestRefreshId) return;
      set((s) => ({
        snapshot,
        meetingEvents,
        visibleSteps: TERMINAL_RUN_STATUSES.has(snapshot.status)
          ? snapshot.steps.length
          : Math.min(s.visibleSteps, snapshot.steps.length),
        error: snapshot.error || null,
      }));
      if (TERMINAL_RUN_STATUSES.has(snapshot.status)) {
        clearTimers();
        set({ polling: snapshot.status === "failed" ? "failed" : "stopped" });
      }
    } catch (err) {
      if (refreshId !== latestRefreshId) return;
      clearTimers();
      set({ polling: "error", error: errorMessage(err) });
    }
  },

  resume: async (groupChatId) => {
    const current = get();
    const storage = browserStorage();
    const persistedRunId = groupChatId && storage
      ? readPersistedRunId(groupChatId, storage)
      : null;
    const targetRunId = groupChatId ? persistedRunId : current.runId;
    const persistedCursor = groupChatId && storage
      ? readPersistedRunCursor(groupChatId, storage)
      : current.eventCursor;
    if (groupChatId && current.runGroupChatId !== groupChatId) {
      set({
        runId: targetRunId,
        runGroupChatId: groupChatId,
        snapshot: null,
        meetingEvents: [],
        visibleSteps: 0,
        polling: "idle",
        error: null,
        eventCursor: persistedCursor,
        connectionState: "closed",
        processedEventIds: {},
        runtimeEvents: [],
      });
    } else if (!current.runId && targetRunId) {
      set({ runId: targetRunId, runGroupChatId: groupChatId ?? current.runGroupChatId });
    }
    if (!get().runId) return;
    // localStorage 只提供 run_id；恢复状态必须由 getRun/getMeetingEvents 返回，绝不启动或合成 Run。
    latestRefreshId += 1;
    clearTimers();
    set({ polling: "running", error: null });
    await get().refresh();
    if (get().runId && get().connectionState !== "connected") openEventStream(get().runId!, get, set);
    if (get().polling === "error") {
      set({ error: `恢复 Run 失败：${get().error ?? "无法读取服务端 Run 状态"}` });
      return;
    }
    if (get().polling === "running") {
      startTimers(get, set);
    }
  },

  stop: () => {
    latestRefreshId += 1;
    clearTimers();
    closeEventStream();
    set({ connectionState: "closed" });
  },

  pause: () => {
    latestRefreshId += 1;
    clearTimers();
    closeEventStream();
    set({ polling: "idle", error: null });
  },

  reset: () => {
    const groupChatId = get().runGroupChatId;
    const storage = browserStorage();
    if (groupChatId && storage) clearPersistedRunId(groupChatId, storage);
    latestRefreshId += 1;
    clearTimers();
    set({
      runId: null,
      runGroupChatId: null,
      snapshot: null,
      meetingEvents: [],
      visibleSteps: 0,
      polling: "idle",
      error: null,
      agentStates: {},
      candidateByAgent: {},
      eventCursor: 0,
      connectionState: "closed",
      processedEventIds: {},
      runtimeEvents: [],
    });
  },

  control: async (action, message) => {
    const { runId } = get();
    if (!runId) return;
    try {
      await controlRun(runId, action, message);
      if (action === "abort") closeEventStream();
      await get().refresh();
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },
}));
