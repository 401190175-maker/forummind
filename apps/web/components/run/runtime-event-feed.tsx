"use client";

import { Badge } from "@/components/ui/badge";
import type { RuntimeEvent } from "@/lib/api";

type Props = {
  events: RuntimeEvent[];
  candidateByAgent: Record<string, string>;
};

/**
 * 候选输出摘要：不再渲染逐条技术事件（agent_id、tool_name、原始事件类型）。
 * 运行时进度改为通过 toChatRunEvent 投影为对话内的安全短句。
 */
export function RuntimeEventFeed({ candidateByAgent }: Props) {
  return (
    <div className="border-b px-4 py-2">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-medium">候选输出</p>
        <Badge variant="outline">等待审阅</Badge>
      </div>
      {Object.keys(candidateByAgent).length > 0 ? (
        <div className="grid gap-2 md:grid-cols-3">
          {Object.entries(candidateByAgent).map(([agentId, content]) => (
            <div
              key={agentId}
              className="rounded-md border bg-amber-50/40 px-2.5 py-2 text-xs dark:bg-amber-950/20"
            >
              <p className="line-clamp-3 whitespace-pre-wrap text-muted-foreground">{content}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground">等待运行产出</p>
      )}
    </div>
  );
}
