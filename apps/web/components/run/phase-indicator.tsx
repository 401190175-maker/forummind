"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { phaseLabel } from "./labels";

type Props = {
  phase: string;
  cycle: number;
  status: string;
  mode: string;
};

/** 固定阶段序列（design.md §8.2，对齐开发计划 §7.1 与竞赛文档 §3.4）。 */
const PHASE_SEQUENCE = [
  "independent_analysis",
  "discussion",
  "review_gate",
  "review_triggered_debate",
  "revision",
  "freeze",
  "meeting",
  "discriminating_experiment",
  "data_import",
  "conclusion",
];

function statusBadge(status: string) {
  if (status === "awaiting_decision") {
    return <Badge variant="warning">⏸ 等待 PI 裁决</Badge>;
  }
  if (status === "conclusion") {
    return <Badge variant="success">已得出结论</Badge>;
  }
  if (status === "completed") {
    return <Badge variant="success">运行完成</Badge>;
  }
  if (status === "terminated") {
    return <Badge variant="secondary">已终止</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">运行失败</Badge>;
  }
  return <Badge variant="secondary">运行中</Badge>;
}

export function PhaseIndicator({ phase, cycle, status, mode }: Props) {
  const currentIndex = PHASE_SEQUENCE.indexOf(phase);

  return (
    <div className="rounded-md border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {PHASE_SEQUENCE.map((p, i) => {
          const done = currentIndex >= 0 && i < currentIndex;
          const current = p === phase;
          return (
            <span
              key={p}
              className={cn(
                "rounded px-2 py-0.5 text-xs",
                current
                  ? "bg-primary/20 font-medium text-primary"
                  : done
                    ? "text-muted-foreground"
                    : "text-muted-foreground/50",
              )}
            >
              {done ? "✓ " : ""}
              {phaseLabel(p)}
            </span>
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <Badge variant="secondary">cycle {cycle}</Badge>
        {statusBadge(status)}
      </div>
    </div>
  );
}
