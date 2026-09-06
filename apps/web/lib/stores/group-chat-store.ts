"use client";

import { create } from "zustand";
import type {
  ChatMessageRecord,
  CreateGroupChatResponse,
  GenerateProfile,
} from "@/lib/api";
import { clearPersistedRunId } from "./run-recovery";

const STORAGE_KEY = "forummind.group-chats.v1";

export type MeetingSchedule = {
  nextMeetingAt: string;
  updatedAt: number;
};

/** 创建结果记录：业务 API 仍是 synthetic demo，浏览器索引可跨路由/刷新恢复。 */
export type GroupChatRecord = {
  id: string;
  topicName: string;
  topicSummary: string;
  members: Array<{
    id: string;
    role: string;
    displayName: string;
    status: string;
    generateProfile: GenerateProfile | null;
    agentProfileRef?: { object_type: string; object_id: string } | null;
    configurationVersion?: string | null;
  }>;
  initialMessages: Array<{ id: string; content: string }>;
  warnings: string[];
  createdAt: number;
  dataSpace: string;
  persistence: string;
  agentAutomation: string;
  projectPhase: string;
  meetingSchedule: MeetingSchedule | null;
};

type PersistedState = {
  records: GroupChatRecord[];
  messagesByGroupId: Record<string, ChatMessageRecord[]>;
};

/** 响应字段映射：snake_case → camelCase，只取本模块需要的字段。 */
export function recordFromResponse(response: CreateGroupChatResponse): GroupChatRecord {
  return {
    id: response.group_chat.id,
    topicName: response.group_chat.topic_name,
    topicSummary: response.group_chat.topic_summary,
    members: response.members.map((m) => ({
      id: m.id,
      role: m.role,
      displayName: m.display_name,
      status: m.status,
      generateProfile: m.generate_profile ?? null,
      agentProfileRef: m.agent_profile_ref ?? null,
      configurationVersion: m.configuration_version ?? null,
    })),
    initialMessages: response.initial_messages.map((m) => ({
      id: m.id,
      content: m.content,
    })),
    warnings: response.warnings ?? [],
    createdAt: Date.now(),
    dataSpace: response.group_chat.data_space,
    persistence: response.persistence,
    agentAutomation: response.agent_automation,
    projectPhase: response.project_phase,
    meetingSchedule: null,
  };
}

function preserveMeetingSchedule(
  record: GroupChatRecord,
  existing: GroupChatRecord | undefined,
): GroupChatRecord {
  return existing?.meetingSchedule === undefined
    ? record
    : { ...record, meetingSchedule: existing.meetingSchedule };
}

type GroupChatStoreState = {
  record: GroupChatRecord | null;
  records: GroupChatRecord[];
  messagesByGroupId: Record<string, ChatMessageRecord[]>;
  hydrated: boolean;
  hydrate: () => void;
  set: (record: GroupChatRecord) => void;
  replaceFromServer: (responses: CreateGroupChatResponse[]) => void;
  select: (groupChatId: string) => void;
  updateMeetingSchedule: (groupChatId: string, schedule: MeetingSchedule | null) => void;
  saveMessages: (groupChatId: string, messages: ChatMessageRecord[]) => void;
  removeCachedGroupChat: (groupChatId: string) => void;
  clear: () => void;
};

function readPersistedState(): PersistedState {
  if (typeof window === "undefined") {
    return { records: [], messagesByGroupId: {} };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { records: [], messagesByGroupId: {} };
    const value = JSON.parse(raw) as Partial<PersistedState>;
    return {
      records: Array.isArray(value.records)
        ? value.records.map((record) => ({
            ...record,
            meetingSchedule: record.meetingSchedule ?? null,
          }))
        : [],
      messagesByGroupId:
        value.messagesByGroupId && typeof value.messagesByGroupId === "object"
          ? value.messagesByGroupId
          : {},
    };
  } catch {
    return { records: [], messagesByGroupId: {} };
  }
}

function persistState(records: GroupChatRecord[], messagesByGroupId: Record<string, ChatMessageRecord[]>) {
  if (typeof window === "undefined") return;
  try {
    const value: PersistedState = { records, messagesByGroupId };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // localStorage is an enhancement; a blocked/private storage mode must not break the app.
  }
}

export const useGroupChatStore = create<GroupChatStoreState>((set, get) => ({
  record: null,
  records: [],
  messagesByGroupId: {},
  hydrated: false,
  hydrate: () => {
    if (get().hydrated) return;
    const persisted = readPersistedState();
    set({
      records: persisted.records,
      messagesByGroupId: persisted.messagesByGroupId,
      record: persisted.records[0] ?? null,
      hydrated: true,
    });
  },
  set: (record) => {
    const stored = preserveMeetingSchedule(
      record,
      get().records.find((item) => item.id === record.id),
    );
    const records = [stored, ...get().records.filter((item) => item.id !== stored.id)];
    persistState(records, get().messagesByGroupId);
    set({ record: stored, records });
  },
  replaceFromServer: (responses) => {
    const current = get();
    const records = responses.map((response) => {
      const record = recordFromResponse(response);
      const existing = current.records.find((item) => item.id === record.id)
        ?? (current.record?.id === record.id ? current.record : undefined);
      return preserveMeetingSchedule(record, existing);
    });
    const selectedId = current.record?.id;
    const record = selectedId
      ? records.find((item) => item.id === selectedId) ?? null
      : null;
    persistState(records, current.messagesByGroupId);
    set({ records, record });
  },
  select: (groupChatId) => {
    const record = get().records.find((item) => item.id === groupChatId) ?? null;
    set({ record });
  },
  updateMeetingSchedule: (groupChatId, schedule) => {
    const records = get().records.map((item) =>
      item.id === groupChatId ? { ...item, meetingSchedule: schedule } : item,
    );
    const record = records.find((item) => item.id === groupChatId) ?? get().record;
    persistState(records, get().messagesByGroupId);
    set({ records, record });
  },
  saveMessages: (groupChatId, messages) => {
    const messagesByGroupId = { ...get().messagesByGroupId, [groupChatId]: messages };
    persistState(get().records, messagesByGroupId);
    set({ messagesByGroupId });
  },
  removeCachedGroupChat: (groupChatId) => {
    const records = get().records.filter((item) => item.id !== groupChatId);
    const messagesByGroupId = { ...get().messagesByGroupId };
    delete messagesByGroupId[groupChatId];
    const record = get().record?.id === groupChatId ? null : get().record;
    const storage = typeof window === "undefined" ? null : window.localStorage;
    if (storage) clearPersistedRunId(groupChatId, storage);
    persistState(records, messagesByGroupId);
    set({ records, messagesByGroupId, record });
  },
  clear: () => {
    if (typeof window !== "undefined") window.localStorage.removeItem(STORAGE_KEY);
    set({ record: null, records: [], messagesByGroupId: {}, hydrated: true });
  },
}));
