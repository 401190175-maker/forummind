"use client";

import { Badge } from "@/components/ui/badge";
import type { ResearchStateChangeView } from "@/lib/api";

type Props = {
  change: ResearchStateChangeView | null;
};

function refText(value: string | null): string {
  return value ?? "初始版本";
}

export function ResearchStateDiff({ change }: Props) {
  if (!change) {
    return (
      <section className="rounded-md border bg-card p-4">
        <p className="text-sm font-medium">暂无状态版本变化摘要</p>
        <p className="mt-1 text-xs text-muted-foreground">
          demo 结果导入后将在这里显示 ResearchState 的只读版本关系。
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3 rounded-md border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">ResearchState 版本变化</p>
          <p className="mt-1 text-xs text-muted-foreground">
            这是新只读状态版本，旧版本仍保留。
          </p>
        </div>
        <Badge variant="outline">{change.supersedes ? "supersedes" : "initial"}</Badge>
      </div>

      <div className="grid gap-2 text-sm md:grid-cols-[1fr_auto_1fr]">
        <div className="rounded-md bg-muted/30 p-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">previous_ref</p>
          <p className="break-all font-mono text-xs">{refText(change.previous_ref)}</p>
        </div>
        <div className="flex items-center justify-center text-muted-foreground">→</div>
        <div className="rounded-md bg-muted/30 p-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">current_ref</p>
          <p className="break-all font-mono text-xs">{change.current_ref ?? "—"}</p>
        </div>
      </div>

      <div className="rounded-md bg-muted/30 p-3">
        <p className="mb-1 text-[11px] font-medium text-muted-foreground">summary</p>
        <p className="break-words text-sm leading-6">{change.summary || "—"}</p>
      </div>

      <div className="grid gap-2 text-sm md:grid-cols-2">
        <div className="rounded-md bg-muted/30 p-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">trigger</p>
          <p className="break-words">{change.trigger || "—"}</p>
        </div>
        <div className="rounded-md bg-muted/30 p-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">
            preserves_old_version
          </p>
          <p>{change.preserves_old_version ? "旧版本仍保留" : "未声明"}</p>
        </div>
      </div>
    </section>
  );
}
