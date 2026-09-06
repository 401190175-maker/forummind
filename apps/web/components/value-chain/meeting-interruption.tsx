"use client";

import { Button } from "@/components/ui/button";
import { appendMeetingMessage } from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import { useRunStore } from "@/lib/stores/run-store";
import { useState } from "react";

type Props = {
  /** 群聊成员（要求回应的 Agent 下拉）。 */
  members: Array<{ id: string; displayName: string }>;
  runId: string;
};

/**
 * 组会插话 UI（design.md §6.5）。
 *
 * PI 在组会期间可以随时插话：输入内容、标记为行动项候选、
 * 选择要求某个 Agent 回应（不选则保留全局插话）。
 * 插话只是会议记录 / 纪要 / 行动项候选，不会绕过审查门改写 ResearchState，
 * 事件写入服务端后由 RunStore 轮询恢复；PI 裁决按钮与 PiDecision 行为不受影响。
 */
export function MeetingInterruption({ members, runId }: Props) {
  const [content, setContent] = useState("");
  const [actionItemCandidate, setActionItemCandidate] = useState(false);
  const [targetAgentId, setTargetAgentId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSend = content.trim().length > 0;

  const targetName = (target: string) => {
    return members.find((m) => m.id === target)?.displayName ?? target;
  };

  const handleSend = async () => {
    if (!canSend || submitting || !runId) return;
    setSubmitting(true);
    setError(null);
    const target = targetAgentId === "" ? null : targetAgentId;
    const labels = [
      actionItemCandidate ? "行动项候选" : null,
      target === null ? null : `要求回应：${targetName(target)}`,
    ].filter((label): label is string => label !== null);
    const persistedContent = labels.length > 0
      ? `[${labels.join("；")}] ${content.trim()}`
      : content.trim();
    try {
      await appendMeetingMessage(runId, persistedContent);
      await useRunStore.getState().refresh();
      setContent("");
      setActionItemCandidate(false);
      setTargetAgentId("");
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "发送插话失败，请重试",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-2 rounded-md border bg-muted/20 p-3">
      <p className="text-sm font-medium">PI 插话（组会讨论）</p>
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={2}
        placeholder="打断争点、追问证据来源、补充实验约束…"
        className="w-full resize-none rounded-md border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary/50"
      />
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={actionItemCandidate}
            onChange={(e) => setActionItemCandidate(e.target.checked)}
          />
          标记为行动项候选
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">要求回应</span>
          <select
            value={targetAgentId}
            onChange={(e) => setTargetAgentId(e.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-xs outline-none focus:border-primary/50"
          >
            <option value="">全局插话（不指定 Agent）</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.displayName}
              </option>
            ))}
          </select>
        </label>
        <div className="flex-1" />
        <Button size="sm" disabled={!canSend} onClick={handleSend}>
          发送插话候选
        </Button>
      </div>
      {error !== null && <p className="text-[11px] text-destructive">{error}</p>}
      <p className="text-[11px] text-muted-foreground">
        插话写入正式组会事件流，不会绕过审查门改写 ResearchState，也不等同 PI 裁决。
      </p>

    </div>
  );
}
