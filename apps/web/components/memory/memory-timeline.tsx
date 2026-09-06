"use client";

import { Badge } from "@/components/ui/badge";

type Props = {
  /** memory_views.timeline 条目（Record 宽松类型，字段安全读取）。 */
  items: Array<Record<string, unknown>>;
};

function formatTime(createdAt: unknown): string {
  if (typeof createdAt !== "number") return "—";
  const date = new Date(createdAt * 1000);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * Memory 时间轴（design.md §2.3）：回答“什么时候发生了什么”。
 * 只读展示同一批 projection 数据。
 */
export function MemoryTimeline({ items }: Props) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground">（暂无 Memory 记录）</p>;
  }
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={str(item.id)} className="flex gap-3 rounded-md border bg-card px-3 py-2">
          <div className="w-36 shrink-0 text-[11px] text-muted-foreground">
            {formatTime(item.created_at)}
          </div>
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary">{str(item.kind)}</Badge>
              {str(item.object_key) !== "" && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  {str(item.object_key)} · v{(item.version as number) ?? 1}
                </span>
              )}
              {str(item.supersedes) !== "" && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  supersedes {str(item.supersedes)}
                </span>
              )}
            </div>
            <p className="text-xs">{str(item.summary)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
