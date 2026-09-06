"use client";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { MeetingEvent } from "@/lib/api";
import type { MeetingData } from "./selectors";
import { PiDecision } from "./pi-decision";
import { MeetingInterruption } from "./meeting-interruption";
import { useGroupChatStore } from "@/lib/stores/group-chat-store";

export const OPTION_LABELS: Record<string, string> = {
  approved: "批准",
  approved_with_conditions: "附条件批准",
  returned: "退回",
  deferred: "暂缓",
  terminated: "终止",
};

type Props = {
  data: MeetingData;
  events: MeetingEvent[];
  awaiting: boolean;
  runId: string;
  onMeetingEnd?: () => void;
};

type SuggestedPayload = { option?: unknown; reason?: unknown };
type DecisionPayload = { option?: unknown; reason?: unknown };

const EVENT_LABELS: Record<string, string> = {
  agent_report: "Agent 汇报",
  message: "PI 插话",
  decision: "PI 决策",
  failure: "运行失败",
};

export function MeetingPanel({ data, events, awaiting, runId, onMeetingEnd }: Props) {
  const members = useGroupChatStore((s) => s.record?.members ?? []);
  return (
    <aside className="flex w-96 shrink-0 flex-col overflow-y-auto border-l bg-card">
      {/* 上半：组会材料 */}
      <div className="space-y-3 p-4">
        <p className="text-sm font-medium">议程</p>
        {data.agenda.length === 0 && <p className="text-xs text-muted-foreground">（空）</p>}
        {data.agenda.map((a) => (
          <p key={a.id} className="text-sm text-muted-foreground">
            {a.content}
          </p>
        ))}
        <p className="text-sm font-medium">未决分歧</p>
        {data.unresolved.length === 0 && <p className="text-xs text-muted-foreground">（空）</p>}
        {data.unresolved.map((u) => (
          <p key={u.id} className="text-sm text-muted-foreground">
            {u.content}
          </p>
        ))}
      </div>

      <Separator />

      <div className="space-y-2 p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">正式组会事件</p>
          <span className="text-[11px] text-muted-foreground">服务端记录</span>
        </div>
        {events.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            当前 Run 尚未产生正式组会事件；案例回放不会伪装成真实汇报。
          </p>
        ) : (
          <div className="space-y-2">
            {events.map((event) => (
              <div
                key={event.id}
                className={
                  event.kind === "failure"
                    ? "rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2"
                    : "rounded-md border bg-muted/20 px-3 py-2"
                }
              >
                <div className="flex items-center justify-between gap-2 text-[11px]">
                  <span className="font-medium">
                    {EVENT_LABELS[event.kind] ?? event.kind}
                  </span>
                  <span className="text-muted-foreground">{event.actor_id}</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm">{event.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <Separator />

      {/* 下半：会议纪要与结构化记录 */}
      <div className="space-y-3 p-4">
        <p className="text-sm font-medium">建议裁决</p>
        {data.suggested.length === 0 && <p className="text-xs text-muted-foreground">（空）</p>}
        {data.suggested.map((s) => {
          const payload = (s.payload ?? {}) as SuggestedPayload;
          const option = typeof payload.option === "string" ? payload.option : "";
          return (
            <p key={s.id} className="text-sm">
              <span className="font-medium">{OPTION_LABELS[option] ?? option}</span>
              <span className="text-muted-foreground">：{s.content}</span>
            </p>
          );
        })}

        {data.decision ? (
          <div className="space-y-1 rounded-md border border-ok/40 bg-ok/10 px-3 py-2">
            <Badge variant="success">已裁决</Badge>
            {(() => {
              const payload = (data.decision.payload ?? {}) as DecisionPayload;
              const option = typeof payload.option === "string" ? payload.option : "";
              return (
                <p className="text-sm">
                  {OPTION_LABELS[option] ?? option}：{data.decision.content}
                </p>
              );
            })()}
          </div>
        ) : awaiting ? (
          <PiDecision runId={runId} />
        ) : (
          <p className="text-xs text-muted-foreground">组会进行中…</p>
        )}
      </div>

      <Separator />

      {onMeetingEnd && (
        <div className="px-4 pt-3">
          <button
            type="button"
            className="w-full rounded-md border border-primary/40 px-3 py-2 text-left text-xs text-primary hover:bg-primary/10"
            onClick={onMeetingEnd}
          >
            宣布组会结束
          </button>
        </div>
      )}

      {/* PI 插话写入正式事件流，不绕过审查门。 */}
      <div className="p-4">
        <MeetingInterruption members={members} runId={runId} />
      </div>
    </aside>
  );
}
