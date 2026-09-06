"use client";

import { Badge } from "@/components/ui/badge";

type Props = {
  /** evidence_graph.nodes：对象节点。 */
  nodes: Array<Record<string, unknown>>;
  /** evidence_graph.edges：关系边（第一版为 supersedes 边）。 */
  edges: Array<Record<string, unknown>>;
};

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * 证据图谱（design.md §2.3、§6.6）：第一版以可读分组列表 + 关系边表呈现。
 * 不引入 React Flow；Claim/Evidence 关系在 payload 稳定后再扩展。
 */
export function EvidenceGraph({ nodes, edges }: Props) {
  if (nodes.length === 0) {
    return <p className="text-xs text-muted-foreground">（暂无图谱节点）</p>;
  }

  // 按 kind 分组展示节点。
  const groups = new Map<string, Array<Record<string, unknown>>>();
  for (const node of nodes) {
    const kind = str(node.kind);
    const list = groups.get(kind) ?? [];
    list.push(node);
    groups.set(kind, list);
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-xs font-medium">对象节点（{nodes.length}）</p>
        <div className="grid gap-2 md:grid-cols-2">
          {[...groups.entries()].map(([kind, items]) => (
            <div key={kind} className="rounded-md border bg-card p-2.5">
              <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">
                {kind}（{items.length}）
              </p>
              <div className="space-y-1">
                {items.map((node) => (
                  <div
                    key={str(node.id)}
                    className="flex items-center gap-2 rounded bg-muted/20 px-2 py-1 text-[11px]"
                  >
                    <span className="font-mono text-muted-foreground">
                      v{(node.version as number) ?? 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate">
                      {str(node.summary)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 text-xs font-medium">关系边（{edges.length}）</p>
        {edges.length === 0 ? (
          <p className="text-xs text-muted-foreground">（无关系边）</p>
        ) : (
          <div className="space-y-1">
            {edges.map((edge, index) => (
              <div
                key={`${str(edge.source)}-${str(edge.target)}-${index}`}
                className="flex items-center gap-2 rounded bg-muted/20 px-2.5 py-1.5 font-mono text-[11px]"
              >
                <span>{str(edge.source)}</span>
                <Badge variant="outline">{str(edge.relation)}</Badge>
                <span>{str(edge.target)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
