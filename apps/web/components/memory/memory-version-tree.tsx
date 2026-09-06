"use client";

import { Badge } from "@/components/ui/badge";

type Props = {
  /** memory_views.version_tree 条目（按对象分组展示版本链）。 */
  items: Array<Record<string, unknown>>;
};

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * Memory 版本树（design.md §2.3）：按对象分组展示版本与 supersedes 关系。
 * 只读展示同一批 projection 数据；不引入图编辑依赖。
 */
export function MemoryVersionTree({ items }: Props) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground">（暂无版本记录）</p>;
  }

  // 按对象（object_key 优先，缺省按 kind）分组。
  const groups = new Map<string, Array<Record<string, unknown>>>();
  for (const item of items) {
    const key = str(item.object_key) !== "" ? str(item.object_key) : str(item.kind);
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }

  return (
    <div className="space-y-3">
      {[...groups.entries()].map(([key, versions]) => (
        <div key={key} className="rounded-md border bg-card p-3">
          <p className="mb-2 text-xs font-medium">
            <span className="font-mono">{key}</span>
            <span className="ml-2 text-muted-foreground">
              {versions.length} 个版本
            </span>
          </p>
          <div className="space-y-1">
            {versions.map((item) => (
              <div
                key={str(item.id)}
                className="flex items-center gap-2 rounded bg-muted/20 px-2.5 py-1.5 text-xs"
              >
                <Badge variant="secondary">v{(item.version as number) ?? 1}</Badge>
                <Badge variant="outline">{str(item.kind)}</Badge>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {str(item.summary)}
                </span>
                {str(item.supersedes) !== "" && (
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                    ↑ supersedes {str(item.supersedes)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
