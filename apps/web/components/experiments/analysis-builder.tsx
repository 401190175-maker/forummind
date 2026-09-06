import { BarChart3, Play } from "lucide-react";
import { useMemo, useState } from "react";

import type { AnalysisOperation, ExperimentDataset } from "@/lib/api";
import { analysisSpecFor, normalizeAnalysisSelection, OPERATION_LABELS } from "./selectors";

export function AnalysisBuilder({
  dataset,
  busy,
  onRun,
}: {
  dataset: ExperimentDataset;
  busy?: boolean;
  onRun: (spec: { operation: AnalysisOperation; column_name: string; compare_column?: string; group_by?: string }) => void;
}) {
  const numericColumns = useMemo(() => Object.entries(dataset.sample_schema).filter(([, type]) => type === "number").map(([name]) => name), [dataset]);
  const groupColumns = useMemo(() => Object.entries(dataset.sample_schema).filter(([, type]) => type === "text" || type === "sample_id").map(([name]) => name), [dataset]);
  const [operation, setOperation] = useState<AnalysisOperation>("summary");
  const [column, setColumn] = useState(numericColumns[0] ?? "");
  const [compare, setCompare] = useState(numericColumns[1] ?? "");
  const [groupBy, setGroupBy] = useState(groupColumns[0] ?? "");
  const normalized = normalizeAnalysisSelection(dataset, { column, compare, groupBy });
  const spec = analysisSpecFor(operation, normalized.column, normalized.compare, normalized.groupBy);

  return (
    <section className="space-y-3 border-t border-border/70 pt-3" aria-label="创建分析">
      <div className="flex items-center gap-2"><BarChart3 className="size-4 text-primary" aria-hidden /><div><p className="text-xs font-semibold">创建分析</p><p className="mt-0.5 text-[11px] text-muted-foreground">仅提供可审计的三种统计操作</p></div></div>
      <div className="grid grid-cols-3 gap-1 border border-border/70 bg-background/40 p-1" role="tablist" aria-label="分析类型">
        {(Object.entries(OPERATION_LABELS) as Array<[AnalysisOperation, string]>).map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={operation === value} onClick={() => setOperation(value)} className={`min-w-0 px-1 py-1.5 text-[11px] ${operation === value ? "bg-primary/15 font-medium text-primary" : "text-muted-foreground hover:bg-secondary/60"}`}>{label}</button>)}
      </div>
      <label className="block text-xs"><span className="mb-1 block text-muted-foreground">{operation === "group_mean" ? "数值列" : "主列"}</span><select value={normalized.column} onChange={(event) => setColumn(event.target.value)} className="h-8 w-full rounded border bg-background px-2 text-xs outline-none focus:border-primary/60">{numericColumns.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      {operation === "correlation" && <label className="block text-xs"><span className="mb-1 block text-muted-foreground">比较列</span><select value={normalized.compare} onChange={(event) => setCompare(event.target.value)} className="h-8 w-full rounded border bg-background px-2 text-xs outline-none focus:border-primary/60"><option value="">选择另一列</option>{numericColumns.filter((item) => item !== normalized.column).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>}
      {operation === "group_mean" && <label className="block text-xs"><span className="mb-1 block text-muted-foreground">分组列</span><select value={normalized.groupBy} onChange={(event) => setGroupBy(event.target.value)} className="h-8 w-full rounded border bg-background px-2 text-xs outline-none focus:border-primary/60"><option value="">选择分组列</option>{groupColumns.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>}
      {operation === "correlation" && <p className="text-[11px] text-warn">相关性只描述变量关系，不代表因果关系。</p>}
      <button type="button" disabled={busy || spec === null} onClick={() => spec && onRun(spec)} className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"><Play className="size-3.5" aria-hidden />{busy ? "分析中…" : "运行分析"}</button>
    </section>
  );
}
