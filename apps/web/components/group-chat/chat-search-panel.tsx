"use client";

import { useEffect, useRef, useState } from "react";
import { searchGroupChatMessages, type ChatMessageRecord } from "@/lib/api";
import { displayNameForSenderId, type TimelineMember } from "./chat-types";

type Props = {
  /** 当前群聊 ID，搜索请求必须绑定该服务端范围。 */
  groupChatId: string;
  /** 群聊成员（群成员筛选下拉）。 */
  members: Array<{
    id: string;
    displayName: string;
    agentProfileRef?: { object_type: string; object_id: string } | null;
  }>;
  /** 关闭搜索面板。 */
  onClose: () => void;
};

/**
 * 聊天记录搜索面板壳（design.md §5.5，tasks.md Task 7）。
 *
 * 由底部对话气泡入口打开，先提供关键词 / 文件 / 日期 / 群成员筛选 UI；
 * 不调用不存在的后端搜索 API，结果区只显示边界说明。
 */
export function ChatSearchPanel({ groupChatId, members, onClose }: Props) {
  const [keyword, setKeyword] = useState("");
  const [fileOnly, setFileOnly] = useState(false);
  const [date, setDate] = useState("");
  const [memberId, setMemberId] = useState("");
  const [results, setResults] = useState<ChatMessageRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestNumber = useRef(0);

  const hasFilters = keyword.trim() !== "" || fileOnly || date !== "" || memberId !== "";
  const timelineMembers: TimelineMember[] = members.map((member) => ({
    id: member.id,
    display_name: member.displayName,
    agent_id: member.agentProfileRef?.object_id?.replace(/^agent:/, "") ?? undefined,
  }));

  useEffect(() => {
    const currentRequest = ++requestNumber.current;
    const timer = window.setTimeout(() => {
      setLoading(true);
      void searchGroupChatMessages(groupChatId, {
        query: keyword.trim(),
        senderId: memberId || undefined,
        dateFrom: date || undefined,
        dateTo: date || undefined,
        attachmentId: fileOnly ? "__attached__" : undefined,
      })
        .then((response) => {
          if (currentRequest !== requestNumber.current) return;
          setResults(response.items);
          setTotal(response.total);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (currentRequest !== requestNumber.current) return;
          setResults([]);
          setTotal(0);
          setError(reason instanceof Error ? reason.message : "搜索请求失败");
        })
        .finally(() => {
          if (currentRequest === requestNumber.current) setLoading(false);
        });
    }, 180);
    return () => window.clearTimeout(timer);
  }, [date, fileOnly, groupChatId, keyword, memberId]);

  return (
    <div className="rounded-md border bg-card p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-sm font-medium">聊天记录搜索</p>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          关闭
        </button>
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="关键词…"
          className="min-w-40 flex-1 basis-48 rounded-md border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary/50"
        />
        <div className="flex min-w-0 flex-1 basis-64 items-center gap-3 text-xs">
          <label className="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
            <input
              type="checkbox"
              checked={fileOnly}
              onChange={(e) => setFileOnly(e.target.checked)}
              className="shrink-0"
            />
            仅文件
          </label>
          <label className="flex min-w-0 flex-1 items-center gap-1.5 whitespace-nowrap">
            <span className="text-muted-foreground">日期</span>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-xs outline-none focus:border-primary/50"
            />
          </label>
        </div>
        <select
          value={memberId}
          onChange={(e) => setMemberId(e.target.value)}
          className="min-w-40 flex-1 basis-48 rounded-md border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary/50"
        >
          <option value="">全部群成员</option>
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.displayName}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1 border-t pt-2 text-xs text-muted-foreground">
        <p>
          当前筛选：
          {keyword.trim() !== "" && `关键词「${keyword.trim()}」`}
          {fileOnly && " 仅文件"}
          {date !== "" && ` 日期 ${date}`}
          {memberId !== "" &&
            ` 成员 ${members.find((m) => m.id === memberId)?.displayName ?? memberId}`}
          {!hasFilters && "（未设置）"}
        </p>
        {loading && <p>正在搜索服务端消息…</p>}
        {error !== null && <p className="text-destructive">搜索失败：{error}</p>}
        {!loading && error === null && (
          <div className="space-y-1.5">
            <p>共 {total} 条匹配消息</p>
            {results.length === 0 && <p>没有匹配的消息。</p>}
            {results.map((message) => (
              <article key={message.id} className="grid gap-1.5 rounded border bg-background p-2 text-foreground sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                <p className="min-w-0 break-words">{message.content}</p>
                <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground sm:flex-col sm:items-end">
                  <span className="truncate">
                    {displayNameForSenderId(message.sender_id, timelineMembers) ?? message.sender_type}
                  </span>
                  <time className="shrink-0" dateTime={new Date(message.created_at * 1000).toISOString()}>
                    {new Date(message.created_at * 1000).toLocaleString()}
                  </time>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
