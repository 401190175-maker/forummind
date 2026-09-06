"use client";

import { Badge } from "@/components/ui/badge";
import type { AgentRuntimeState } from "@/lib/stores/run-store";

type Props = {
  agents: Array<Record<string, unknown>>;
  states: Record<string, AgentRuntimeState>;
};

const labels: Record<AgentRuntimeState, string> = {
  idle: "待命", analyzing: "分析中", tool: "调用工具", reviewing: "审查中",
  completed: "已完成", aborted: "已中止", failed: "失败",
};

function text(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

export function AgentLane({ agents, states }: Props) {
  return (
    <div className="flex gap-2 overflow-x-auto border-b bg-muted/20 px-4 py-2">
      {agents.map((agent) => {
        const id = text(agent.agent_id, "unknown");
        const state = states[id] ?? "idle";
        return (
          <div key={id} className="flex min-w-36 items-center justify-between gap-3 rounded-md border bg-card px-3 py-2 text-xs">
            <div className="min-w-0">
              <p className="truncate font-medium">{text(agent.name ?? agent.display_name, id)}</p>
              <p className="truncate text-[11px] text-muted-foreground">{text(agent.role, id)}</p>
            </div>
            <Badge variant={state === "failed" ? "destructive" : state === "completed" ? "success" : "secondary"}>
              {labels[state]}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}
