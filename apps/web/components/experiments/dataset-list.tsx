import { ChevronRight, Database, RefreshCw } from "lucide-react";

import type { DatasetVersionRef, ExperimentDatasetSummary } from "@/lib/api";
import { datasetLabel } from "./selectors";

export function DatasetList({
  datasets,
  selectedRefs,
  loading,
  onOpen,
  onRefresh,
}: {
  datasets: ExperimentDatasetSummary[];
  selectedRefs: DatasetVersionRef[];
  loading?: boolean;
  onOpen: (datasetId: string) => void;
  onRefresh: () => void;
}) {
  return (
    <section className="space-y-2" aria-label="实验数据集">
      <div className="flex items-center justify-between gap-2">
        <div><p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">数据集</p><p className="mt-1 text-[11px] text-muted-foreground">按课题组保存的不可变版本</p></div>
        <button type="button" className="rounded p-1.5 text-muted-foreground hover:bg-secondary/60 hover:text-foreground" onClick={onRefresh} disabled={loading} title="刷新数据集" aria-label="刷新数据集"><RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden /></button>
      </div>
      {datasets.length === 0 ? <p className="border border-dashed border-border/70 px-3 py-4 text-xs text-muted-foreground">还没有导入的数据集。</p> : (
        <div className="space-y-1">
          {datasets.map((dataset) => {
            const selected = selectedRefs.find((ref) => ref.dataset_id === dataset.dataset_id);
            return (
              <button type="button" key={dataset.dataset_id} onClick={() => onOpen(dataset.dataset_id)} className="flex w-full items-center gap-2 border border-border/70 bg-background/40 px-2.5 py-2 text-left hover:border-primary/50 hover:bg-primary/5">
                <span className="flex size-7 shrink-0 items-center justify-center border border-primary/20 bg-primary/10 text-primary"><Database className="size-3.5" aria-hidden /></span>
                <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium">{dataset.filename}</span><span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{datasetLabel(dataset)}</span>{selected && <span className="mt-1 inline-flex text-[10px] text-ok">已选 v{selected.version}</span>}</span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
