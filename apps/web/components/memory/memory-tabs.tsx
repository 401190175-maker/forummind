"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { MemoryEntry, MemoryViews } from "@/lib/api";
import { useRunStore } from "@/lib/stores/run-store";
import { MemoryTimeline } from "./memory-timeline";
import { MemoryVersionTree } from "./memory-version-tree";
import { EvidenceGraph } from "./evidence-graph";

const SUMMARY_FIELDS = ["statement", "summary", "content", "mechanism_draft", "option"];

function entrySummary(entry: MemoryEntry): string {
  const payload = (entry.payload ?? {}) as Record<string, unknown>;
  for (const key of SUMMARY_FIELDS) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "（无摘要）";
}

/** 从 raw memory entries 降级生成最小三视图（design §7.1 fallback）。 */
export function memoryViewsFromEntries(entries: MemoryEntry[]): MemoryViews {
  const sorted = [...entries].sort((a, b) => a.created_at - b.created_at);
  const timeline = sorted.map((e) => ({
    id: e.id,
    kind: e.kind,
    object_key: e.object_key,
    version: e.version,
    supersedes: e.supersedes,
    created_at: e.created_at,
    summary: entrySummary(e),
    data_space: e.data_space,
  }));
  const versionTree = [...timeline].sort((a, b) => {
    const ka = (a.object_key as string) ?? (a.kind as string);
    const kb = (b.object_key as string) ?? (b.kind as string);
    return ka.localeCompare(kb) || (a.version as number) - (b.version as number);
  });
  const nodes = timeline.map(({ id, kind, object_key, version, summary }) => ({
    id,
    kind,
    object_key,
    version,
    summary,
  }));
  const edges = timeline
    .filter((e) => e.supersedes !== null)
    .map((e) => ({
      source: e.id,
      target: e.supersedes,
      relation: "supersedes",
    }));
  return {
    timeline,
    version_tree: versionTree,
    evidence_graph: { nodes, edges },
  };
}

const TABS = [
  { value: "timeline", label: "时间轴" },
  { value: "tree", label: "版本树" },
  { value: "graph", label: "证据图谱" },
] as const;

/**
 * Memory 三视图容器（design.md §2.3，tasks.md Task 11）。
 *
 * 三个视图共享同一批 Memory 数据（优先 `memory_views`，
 * 缺失时从 raw `memory` 降级生成最小视图）；不引入 React Flow。
 */
export function MemoryTabs() {
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("timeline");
  const snapshot = useRunStore((s) => s.snapshot);
  const isFallback = !snapshot?.memory_views;
  const views: MemoryViews =
    snapshot?.memory_views ?? memoryViewsFromEntries(snapshot?.memory ?? []);

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="inline-flex rounded-md border bg-muted/40 p-0.5">
          {TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => setTab(t.value)}
              className={cn(
                "rounded px-3 py-1 text-xs font-medium transition-colors",
                tab === t.value
                  ? "bg-secondary text-secondary-foreground shadow"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        {isFallback && (
          <Badge variant="outline">Memory 视图为 raw 降级（demo）</Badge>
        )}
      </div>

      {tab === "timeline" && <MemoryTimeline items={views.timeline} />}
      {tab === "tree" && <MemoryVersionTree items={views.version_tree} />}
      {tab === "graph" && (
        <EvidenceGraph
          nodes={views.evidence_graph.nodes}
          edges={views.evidence_graph.edges}
        />
      )}
    </div>
  );
}
