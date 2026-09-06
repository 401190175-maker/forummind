import { Download } from "lucide-react";

import type { ExperimentDataset } from "@/lib/api";

export function DatasetVersionDetail({
  dataset,
  downloadUrl,
}: {
  dataset: ExperimentDataset;
  downloadUrl: string;
}) {
  const columns = Object.keys(dataset.sample_schema);
  return (
    <section className="space-y-3 border-t border-border/70 pt-3" aria-label={`数据集 v${dataset.version} 详情`}>
      <div className="flex items-start justify-between gap-2"><div><p className="text-xs font-semibold">v{dataset.version} 数据快照</p><p className="mt-1 text-[11px] text-muted-foreground">{dataset.filename} · {dataset.rows.length} 行</p></div><a className="rounded p-1.5 text-muted-foreground hover:bg-secondary/60 hover:text-foreground" href={downloadUrl} title="下载源文件" aria-label="下载源文件"><Download className="size-3.5" aria-hidden /></a></div>
      <div className="grid grid-cols-2 gap-2 text-[11px]"><div><span className="text-muted-foreground">字段</span><p className="mt-0.5 truncate">{columns.join("、")}</p></div><div><span className="text-muted-foreground">状态</span><p className="mt-0.5">{dataset.verification_status === "verified" ? "来源已校验" : "来源待校验"}</p></div></div>
      {Object.keys(dataset.units).length > 0 && <p className="text-[11px] text-muted-foreground">单位：{Object.entries(dataset.units).map(([key, value]) => `${key}=${value}`).join(" · ")}</p>}
      <div className="overflow-x-auto border border-border/70"><table className="w-full min-w-[28rem] text-left text-[11px]"><thead className="bg-muted/30 text-muted-foreground"><tr><th className="px-2 py-1.5">行</th>{columns.map((column) => <th key={column} className="px-2 py-1.5">{column}</th>)}</tr></thead><tbody>{dataset.rows.slice(0, 8).map((row) => <tr key={row.row_number} className="border-t border-border/60"><td className="px-2 py-1.5 text-muted-foreground">{row.row_number}</td>{columns.map((column) => <td key={column} className="max-w-32 truncate px-2 py-1.5">{String(row.values[column] ?? "")}</td>)}</tr>)}</tbody></table></div>
    </section>
  );
}
