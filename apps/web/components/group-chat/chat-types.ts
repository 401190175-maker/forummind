/**
 * 聊天时间轴的安全投影（design §4.6）。
 *
 * 把后端 ChatMessageRecord 映射为 UI 只需要的左/右气泡数据，
 * 隐藏 data_space、persistence、运行状态码等实现元数据。
 * 未知 kind 一律回退为纯文本气泡，绝不导致时间轴崩溃。
 */

import type { ChatMessageRecord } from "@/lib/api";

export type ChatSide = "left" | "right";

export interface TimelineMember {
  id: string;
  display_name: string;
  role?: string;
  agent_id?: string;
}

export type ChatTimelineItem = {
  id: string;
  side: ChatSide;
  senderName: string;
  kind: string;
  content: string;
  payload: Record<string, unknown>;
  createdAt: number;
};

const POSTDOC_DEFAULT_NAME = "博士后";
const SYSTEM_SENDER_NAMES: Record<string, string> = {
  postdoc: POSTDOC_DEFAULT_NAME,
};

/** Resolve server sender IDs to the stable display name selected for the group member. */
export function displayNameForSenderId(
  senderId: string | null | undefined,
  members: TimelineMember[] = [],
): string | null {
  if (!senderId) return null;
  const normalizeAgentId = (value: string) => value.replace(/^agent:/, "");
  const normalizedSenderId = normalizeAgentId(senderId);
  return members.find(
    (candidate) =>
      candidate.id === senderId ||
      candidate.agent_id === senderId ||
      normalizeAgentId(candidate.id) === normalizedSenderId ||
      (candidate.agent_id !== undefined && normalizeAgentId(candidate.agent_id) === normalizedSenderId),
  )?.display_name ?? null;
}

/** 把一条后端消息映射为安全的 UI 时间轴项。 */
export function toTimelineItem(
  message: ChatMessageRecord,
  members: TimelineMember[] = [],
): ChatTimelineItem {
  const side: ChatSide = message.sender_type === "user" ? "right" : "left";
  const memberName = displayNameForSenderId(message.sender_id, members);
  const senderName =
    memberName ??
    (message.sender_id && message.sender_id !== "system"
      ? SYSTEM_SENDER_NAMES[message.sender_id] ?? message.sender_id
      : POSTDOC_DEFAULT_NAME);

  return {
    id: message.id,
    side,
    senderName,
    kind: message.kind ?? "text",
    content: message.content,
    payload: (message.payload ?? {}) as Record<string, unknown>,
    createdAt: message.created_at,
  };
}
