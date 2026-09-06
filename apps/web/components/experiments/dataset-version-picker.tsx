import { Check, Circle } from "lucide-react";

import type { DatasetVersionRef, ExperimentDataset } from "@/lib/api";

export function DatasetVersionPicker({
  versions,
  selected,
  activeVersion,
  onSelect,
}: {
  versions: ExperimentDataset[];
  selected: DatasetVersionRef | undefined;
  activeVersion: number | null;
  onSelect: (version: number) => void;
}) {
  return (
    <div className="space-y-1.5" aria-label="数据集版本">
      <p className="text-xs font-semibold">不可变版本</p>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {versions.slice().sort((a, b) => b.version - a.version).map((version) => {
          const isSelected = selected?.version === version.version;
          return (
            <button key={version.version} type="button" onClick={() => onSelect(version.version)} className={`flex items-center gap-2 border px-2.5 py-2 text-left text-xs ${activeVersion === version.version ? "border-primary/60 bg-primary/10" : "border-border/70 bg-background/30 hover:border-primary/40"}`}>
              {isSelected ? <Check className="size-3.5 shrink-0 text-ok" aria-hidden /> : <Circle className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />}
              <span className="min-w-0"><span className="block font-medium">v{version.version}{isSelected ? " · 用于下次分析" : ""}</span><span className="mt-0.5 block text-[11px] text-muted-foreground">{version.rows.length} 行 · {Object.keys(version.sample_schema).length} 个字段</span></span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
