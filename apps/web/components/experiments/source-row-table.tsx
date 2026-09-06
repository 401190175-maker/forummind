import { ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";

import type { ExperimentDataset, SourceRowRef } from "@/lib/api";
import { findSourceRow, sourceRefsForPage } from "./selectors";

export function SourceRowTable({
  dataset,
  refs,
  onSelect,
}: {
  dataset: ExperimentDataset | null;
  refs: SourceRowRef[];
  onSelect: (ref: SourceRowRef) => void;
}) {
  const [page, setPage] = useState(0);
  const visible = sourceRefsForPage(refs, page);
  const hasMore = (page + 1) * 12 < refs.length;
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-muted-foreground">显示第 {page + 1} 页来源定位，共 {refs.length} 条。</p>
      <div className="overflow-x-auto border border-border/70"><table className="w-full min-w-[28rem] text-left text-[11px]"><thead className="bg-muted/30 text-muted-foreground"><tr><th className="px-2 py-1.5">行</th><th className="px-2 py-1.5">字段</th><th className="px-2 py-1.5">值</th><th className="px-2 py-1.5">操作</th></tr></thead><tbody>{visible.map((ref) => { const row = findSourceRow(dataset, ref); return <tr key={`${ref.row_number}-${ref.column_name}`} className="border-t border-border/60"><td className="px-2 py-1.5">{ref.row_number}</td><td className="px-2 py-1.5">{ref.column_name}</td><td className="max-w-32 truncate px-2 py-1.5">{String(row?.values[ref.column_name] ?? "暂无")}</td><td className="px-2 py-1.5"><button type="button" onClick={() => onSelect(ref)} className="inline-flex items-center gap-1 text-primary hover:underline" title="查看来源详情"><ExternalLink className="size-3" aria-hidden />查看</button></td></tr>; })}</tbody></table></div>
      {hasMore && <button type="button" onClick={() => setPage((value) => value + 1)} className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"><ChevronDown className="size-3.5" aria-hidden />加载更多来源</button>}
    </div>
  );
}
