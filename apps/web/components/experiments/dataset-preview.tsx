import { AlertCircle, Check, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { ExperimentFieldType, ExperimentPreview } from "@/lib/api";
import { formatFinding } from "./selectors";

const FIELD_TYPES: Array<{ value: ExperimentFieldType; label: string }> = [
  { value: "sample_id", label: "样品 ID" },
  { value: "number", label: "数值" },
  { value: "text", label: "文本" },
];

export function DatasetPreview({
  preview,
  busy,
  onCancel,
  onImport,
}: {
  preview: ExperimentPreview;
  busy?: boolean;
  onCancel: () => void;
  onImport: (sampleSchema: Record<string, ExperimentFieldType>, units: Record<string, string>) => void;
}) {
  const [schema, setSchema] = useState(preview.inferred_field_types);
  const [units, setUnits] = useState<Record<string, string>>({});

  useEffect(() => {
    setSchema(preview.inferred_field_types);
    setUnits({});
  }, [preview]);

  return (
    <section className="space-y-3 border-b border-border/70 pb-4" aria-label="实验数据预览">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{preview.filename}</p>
          <p className="mt-1 text-xs text-muted-foreground">确认字段类型后才会创建数据集版本</p>
        </div>
        <button type="button" className="shrink-0 text-muted-foreground hover:text-foreground" onClick={onCancel} title="取消预览" aria-label="取消预览">
          <X className="size-4" aria-hidden />
        </button>
      </div>

      {preview.validation_findings.length > 0 && (
        <div className="space-y-1 border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
          <div className="flex items-center gap-1.5 font-medium"><AlertCircle className="size-3.5" aria-hidden />需要检查</div>
          {preview.validation_findings.slice(0, 5).map((finding, index) => <p key={index}>{formatFinding(finding)}</p>)}
        </div>
      )}

      <div className="space-y-2">
        {preview.columns.map((column) => (
          <div key={column} className="grid grid-cols-[minmax(0,1fr)_7rem] items-center gap-2">
            <label className="min-w-0">
              <span className="block truncate text-xs font-medium">{column}</span>
              {schema[column] === "number" && (
                <input
                  value={units[column] ?? ""}
                  onChange={(event) => setUnits((current) => ({ ...current, [column]: event.target.value }))}
                  placeholder="单位（可选）"
                  className="mt-1 h-7 w-full rounded border bg-background px-2 text-[11px] outline-none focus:border-primary/60"
                />
              )}
            </label>
            <select
              value={schema[column] ?? "text"}
              onChange={(event) => setSchema((current) => ({ ...current, [column]: event.target.value as ExperimentFieldType }))}
              className="h-8 min-w-0 rounded border bg-background px-2 text-xs outline-none focus:border-primary/60"
              aria-label={`${column} 字段类型`}
            >
              {FIELD_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
            </select>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto border border-border/70">
        <table className="w-full min-w-[28rem] text-left text-[11px]">
          <thead className="bg-muted/30 text-muted-foreground"><tr>{preview.columns.map((column) => <th key={column} className="px-2 py-1.5 font-medium">{column}</th>)}</tr></thead>
          <tbody>{preview.sample_rows.slice(0, 3).map((row, index) => <tr key={index} className="border-t border-border/60">{preview.columns.map((column) => <td key={column} className="max-w-32 truncate px-2 py-1.5">{String(row[column] ?? "")}</td>)}</tr>)}</tbody>
        </table>
      </div>

      <div className="flex items-center justify-end gap-2">
        <button type="button" className="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs text-muted-foreground hover:bg-secondary/60 hover:text-foreground" onClick={onCancel}>
          <X className="size-3.5" aria-hidden />取消
        </button>
        <button type="button" disabled={busy} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50" onClick={() => onImport(schema, units)}>
          <Check className="size-3.5" aria-hidden />{busy ? "导入中…" : "确认导入"}
        </button>
      </div>
    </section>
  );
}
