import { ExternalLink, TriangleAlert } from "lucide-react";

import type { AnalysisResult } from "@/lib/api";
import { displayResultValue, operationLabel, sourceRefLabel, verificationLabel } from "./selectors";

export function AnalysisResultView({
  result,
  onSource,
}: {
  result: AnalysisResult;
  onSource: (ref: AnalysisResult["provenance"][number]) => void;
}) {
  return (
    <article className="space-y-3 border border-border/70 bg-background/30 p-3" aria-label="分析结果">
      <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold">{operationLabel(result.operation)} · v{result.dataset_version}</p><p className="mt-1 text-[11px] text-muted-foreground">{new Date(result.created_at * 1000).toLocaleString()} · {result.column_name}</p></div><span className="text-[10px] text-ok">可追溯</span></div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{Object.entries(result.result).map(([key, value]) => <div key={key} className="border border-border/60 px-2 py-1.5"><span className="block text-[10px] text-muted-foreground">{key}</span><span className="mt-0.5 block truncate text-xs font-medium">{displayResultValue(value)}</span></div>)}</div>
      {result.warnings.map((warning) => <p key={warning} className="flex items-start gap-1.5 text-[11px] text-warn"><TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />{warning === "correlation_not_causation" ? "相关性不等于因果关系。" : warning}</p>)}
      <div className="flex items-center justify-between gap-2"><p className="text-[11px] text-muted-foreground">来源 {Math.min(result.provenance.length, 12)} / {result.provenance.length}</p><div className="flex flex-wrap justify-end gap-1">{result.provenance.slice(0, 4).map((ref) => <button key={`${ref.row_number}-${ref.column_name}`} type="button" onClick={() => onSource(ref)} title={`${sourceRefLabel(ref)} · ${verificationLabel(ref.verification_status)}`} className="inline-flex items-center gap-1 rounded border border-primary/25 px-2 py-1 text-[10px] text-primary hover:bg-primary/10"><ExternalLink className="size-3" aria-hidden />第 {ref.row_number} 行</button>)}</div></div>
    </article>
  );
}
