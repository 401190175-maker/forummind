import { History } from "lucide-react";

import type { AnalysisResult } from "@/lib/api";
import { operationLabel, sortAnalysesByCreatedAt } from "./selectors";

export function AnalysisHistory({
  analyses,
  onOpen,
}: {
  analyses: AnalysisResult[];
  onOpen: (analysis: AnalysisResult) => void;
}) {
  return (
    <section className="space-y-2 border-t border-border/70 pt-3" aria-label="分析历史">
      <div className="flex items-center gap-2"><History className="size-3.5 text-muted-foreground" aria-hidden /><p className="text-xs font-semibold">分析历史</p></div>
      {analyses.length === 0 ? <p className="text-[11px] text-muted-foreground">选择版本后，运行过的分析会留在这里。</p> : <div className="space-y-1">{sortAnalysesByCreatedAt(analyses).map((analysis) => <button type="button" key={analysis.analysis_id} onClick={() => onOpen(analysis)} className="flex w-full items-center justify-between gap-2 border border-border/60 px-2.5 py-2 text-left hover:border-primary/40 hover:bg-primary/5"><span className="min-w-0"><span className="block truncate text-xs font-medium">{operationLabel(analysis.operation)}</span><span className="mt-0.5 block text-[11px] text-muted-foreground">v{analysis.dataset_version} · {analysis.column_name}</span></span><span className="shrink-0 text-[10px] text-muted-foreground">{new Date(analysis.created_at * 1000).toLocaleDateString()}</span></button>)}</div>}
    </section>
  );
}
