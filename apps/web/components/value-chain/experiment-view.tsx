"use client";

import { useMemo, useState } from "react";

import { MemoryTabs } from "@/components/memory/memory-tabs";
import { importResults } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useRunStore } from "@/lib/stores/run-store";
import { experimentViewFromSnapshot } from "./experiment-selectors";
import { ExperimentCard } from "./experiment-card";
import { ExperimentResults } from "./experiment-results";
import { HypothesisUpdates } from "./hypothesis-updates";
import { ResearchStateDiff } from "./research-state-diff";

const TABS = [
  { value: "experiment", label: "实验视图" },
  { value: "memory", label: "Memory" },
] as const;

export function ExperimentView() {
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("experiment");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const snapshot = useRunStore((s) => s.snapshot);
  const runId = useRunStore((s) => s.runId);
  const refresh = useRunStore((s) => s.refresh);
  const view = useMemo(() => {
    if (!snapshot) return null;
    return snapshot?.experiment_view ?? experimentViewFromSnapshot(snapshot);
  }, [snapshot]);
  const canImport = snapshot?.phase === "discriminating_experiment" && Boolean(runId);

  async function handleImport() {
    if (!runId || importing || snapshot?.phase !== "discriminating_experiment") return;
    setImporting(true);
    setImportError(null);
    try {
      await importResults(runId);
      await refresh();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "导入 demo 结果失败");
    } finally {
      setImporting(false);
    }
  }

  if (!snapshot || !view) {
    return (
      <div className="p-4">
        <p className="text-sm text-muted-foreground">暂无实验视图数据。</p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="inline-flex rounded-md border bg-muted/40 p-0.5">
          {TABS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setTab(item.value)}
              className={cn(
                "rounded px-3 py-1 text-xs font-medium transition-colors",
                tab === item.value
                  ? "bg-secondary text-secondary-foreground shadow"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {canImport && (
            <button
              type="button"
              onClick={() => void handleImport()}
              disabled={importing}
              className="rounded-md border bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-secondary/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {importing ? "导入中..." : "导入 demo 结果"}
            </button>
          )}
          <span className="text-xs text-muted-foreground">data_space: {view.data_space}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "memory" ? (
          <MemoryTabs />
        ) : (
          <div className="space-y-4 p-4">
            {importError && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                {importError}
              </div>
            )}
            <ExperimentCard plan={view.plan} />
            <ExperimentResults results={view.results} />
            <HypothesisUpdates updates={view.hypothesis_updates} />
            <ResearchStateDiff change={view.research_state_change} />
            <section className="rounded-md border bg-card p-4">
              <p className="mb-2 text-sm font-medium">边界说明</p>
              <ul className="space-y-1 text-xs leading-5 text-muted-foreground">
                {view.boundary_notes.map((note, index) => (
                  <li key={`${note}-${index}`} className="break-words">
                    {note}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
