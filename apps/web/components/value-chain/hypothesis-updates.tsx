"use client";

import { Badge } from "@/components/ui/badge";
import type { HypothesisUpdateView } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  updates: HypothesisUpdateView[];
};

const STATUS_META: Record<string, { label: string; className: string }> = {
  supported: {
    label: "支持程度上调",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700",
  },
  weakened: {
    label: "支持程度下调",
    className: "border-rose-500/30 bg-rose-500/10 text-rose-700",
  },
  inconclusive: {
    label: "不可判别",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-700",
  },
  posterior: {
    label: "后验假设",
    className: "border-sky-500/30 bg-sky-500/10 text-sky-700",
  },
};

function statusMeta(status: string) {
  return STATUS_META[status] ?? {
    label: "未知状态",
    className: "border-muted-foreground/30 bg-muted/40 text-muted-foreground",
  };
}

export function HypothesisUpdates({ updates }: Props) {
  if (updates.length === 0) {
    return (
      <section className="rounded-md border bg-card p-4">
        <p className="text-sm font-medium">暂无假设更新</p>
        <p className="mt-1 text-xs text-muted-foreground">
          demo 结果导入后将在这里显示 Claim 状态变化。
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3 rounded-md border bg-card p-4">
      <div>
        <p className="text-sm font-semibold">假设更新</p>
        <p className="mt-1 text-xs text-muted-foreground">
          状态表示支持程度变化，不表示因果机制已被证明。
        </p>
      </div>

      <div className="space-y-2">
        {updates.map((update, index) => {
          const meta = statusMeta(update.status);
          return (
            <article
              key={`${update.claim_id}-${index}`}
              className="rounded-md border bg-muted/20 p-3"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">
                  {update.claim_id || "—"}
                </span>
                <Badge variant="outline" className={cn("border", meta.className)}>
                  {meta.label}
                </Badge>
              </div>
              <p className="break-words text-sm leading-6">{update.reason || "—"}</p>
              <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">
                {update.causal_boundary || "支持程度变化不等于因果证明"}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
