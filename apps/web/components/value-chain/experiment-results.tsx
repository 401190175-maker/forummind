"use client";

import { Badge } from "@/components/ui/badge";
import type { ExperimentResultsView } from "@/lib/api";

type Props = {
  results: ExperimentResultsView | null;
};

function formatTime(value: number | null): string {
  if (value === null) return "—";
  return new Date(value * 1000).toLocaleString("zh-CN");
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export function ExperimentResults({ results }: Props) {
  if (!results) {
    return (
      <section className="rounded-md border bg-card p-4">
        <p className="text-sm font-medium">尚未导入 demo 结果</p>
        <p className="mt-1 text-xs text-muted-foreground">
          导入后将在这里显示 synthetic demo 来源、核查摘要与结果行。
        </p>
      </section>
    );
  }

  const columns = Array.from(new Set(results.rows.flatMap((row) => Object.keys(row))));

  return (
    <section className="space-y-3 rounded-md border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">实验结果导入</p>
          <p className="mt-1 text-xs text-muted-foreground">
            synthetic demo 结果，不代表真实实验文件。
          </p>
        </div>
        <Badge variant="outline">source: {results.source || "—"}</Badge>
      </div>

      <div className="grid gap-2 text-sm md:grid-cols-2">
        <div className="rounded-md bg-muted/30 p-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">导入时间</p>
          <p>{formatTime(results.imported_at)}</p>
        </div>
        <div className="rounded-md bg-muted/30 p-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">核查摘要</p>
          <p className="break-words leading-6">{results.validation_summary || "—"}</p>
        </div>
      </div>

      <div className="rounded-md bg-muted/30 p-3">
        <p className="mb-1 text-[11px] font-medium text-muted-foreground">导入说明</p>
        <p className="break-words text-sm leading-6">{results.notes || "—"}</p>
      </div>

      <div>
        <p className="mb-2 text-xs font-medium">结果行摘要（{results.rows.length}）</p>
        {results.rows.length === 0 || columns.length === 0 ? (
          <p className="text-xs text-muted-foreground">—</p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full min-w-max text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground">
                <tr>
                  {columns.map((column) => (
                    <th key={column} className="px-3 py-2 font-medium">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.rows.map((row, index) => (
                  <tr key={index} className="border-t">
                    {columns.map((column) => (
                      <td key={column} className="max-w-64 break-words px-3 py-2">
                        {cell(row[column])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
