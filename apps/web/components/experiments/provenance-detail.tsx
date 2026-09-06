import { ArrowLeft, Download, MapPin } from "lucide-react";

import type { ExperimentDataset, SourceRowRef } from "@/lib/api";
import { findSourceRow, verificationLabel } from "./selectors";

export function ProvenanceDetail({
  dataset,
  ref,
  downloadUrl,
  onBack,
}: {
  dataset: ExperimentDataset | null;
  ref: SourceRowRef;
  downloadUrl: string | null;
  onBack: () => void;
}) {
  const row = findSourceRow(dataset, ref);
  return (
    <section className="space-y-4" aria-label="来源详情">
      <div className="flex items-center justify-between gap-2"><button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" aria-hidden />返回分析</button>{downloadUrl && <a href={downloadUrl} className="rounded p-1.5 text-muted-foreground hover:bg-secondary/60 hover:text-foreground" title="下载源文件" aria-label="下载源文件"><Download className="size-3.5" aria-hidden /></a>}</div>
      <div><div className="flex items-center gap-2"><MapPin className="size-4 text-primary" aria-hidden /><p className="text-sm font-semibold">来源定位</p></div><p className="mt-1 text-xs text-muted-foreground">{dataset?.filename ?? "源文件"} · v{ref.dataset_version} · 第 {ref.row_number} 行 · {ref.column_name}</p></div>
      <dl className="grid gap-2 text-xs"><div className="border border-border/60 px-3 py-2"><dt className="text-[11px] text-muted-foreground">来源状态</dt><dd className="mt-1">{verificationLabel(ref.verification_status)}</dd></div><div className="border border-border/60 px-3 py-2"><dt className="text-[11px] text-muted-foreground">引用值</dt><dd className="mt-1 break-words font-mono">{String(row?.values[ref.column_name] ?? "暂无")}</dd></div><div className="border border-border/60 px-3 py-2"><dt className="text-[11px] text-muted-foreground">文件位置</dt><dd className="mt-1 break-all text-muted-foreground">{ref.source_location}</dd></div></dl>
      {!row && <p className="border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">当前版本没有找到该行，源文件可能暂时不可用。可以下载源文件后重新定位。</p>}
    </section>
  );
}
