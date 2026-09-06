import type {
  AnalysisOperation,
  AnalysisSpec,
  DatasetVersionRef,
  ExperimentDataset,
  ExperimentDatasetSummary,
  AnalysisResult,
  SourceRowRef,
} from "@/lib/api";

const FINDING_LABELS: Record<string, string> = {
  invalid_number: "数值格式无效",
  duplicate_sample_id: "样品 ID 重复",
  missing_value: "缺少值",
  missing_sample_id: "缺少样品 ID",
  unsupported_field_type: "字段类型不支持",
};

export const OPERATION_LABELS: Record<AnalysisOperation, string> = {
  summary: "单列摘要",
  correlation: "相关性",
  group_mean: "分组均值",
};

export function datasetLabel(dataset: ExperimentDatasetSummary): string {
  return `${dataset.filename} · ${dataset.row_count} 行 · 最新 v${dataset.latest_version}`;
}

export function selectedDatasetSummary(
  datasets: ExperimentDatasetSummary[],
  refs: DatasetVersionRef[],
): { count: number; labels: string[] } {
  return {
    count: refs.length,
    labels: refs.map((ref) => {
      const dataset = datasets.find((item) => item.dataset_id === ref.dataset_id);
      return dataset ? `${dataset.filename} · v${ref.version}` : `数据集 · v${ref.version}`;
    }),
  };
}

export function isSupportedExperimentFileName(name: string): boolean {
  return /\.(csv|xlsx)$/i.test(name.trim());
}

export function formatFinding(finding: Record<string, unknown>): string {
  const row = typeof finding.row_number === "number" ? `第 ${finding.row_number} 行` : "数据行";
  const column = typeof finding.column_name === "string" ? finding.column_name : "字段";
  const code = typeof finding.code === "string" ? finding.code : "validation_error";
  const message = typeof finding.message === "string"
    ? finding.message
    : FINDING_LABELS[code] ?? "数据格式需要检查";
  return `${row} · ${column}：${message}`;
}

export function analysisSpecFor(
  operation: AnalysisOperation,
  columnName: string,
  compareColumn: string,
  groupBy: string,
): AnalysisSpec | null {
  if (!columnName) return null;
  if (operation === "summary") return { operation, column_name: columnName };
  if (operation === "correlation") {
    if (!compareColumn || compareColumn === columnName) return null;
    return { operation, column_name: columnName, compare_column: compareColumn };
  }
  if (!groupBy) return null;
  return { operation, column_name: columnName, group_by: groupBy };
}

export function normalizeAnalysisSelection(
  dataset: Pick<ExperimentDataset, "sample_schema">,
  selection: { column: string; compare: string; groupBy: string },
): { column: string; compare: string; groupBy: string } {
  const numericColumns = Object.entries(dataset.sample_schema)
    .filter(([, type]) => type === "number")
    .map(([name]) => name);
  const groupColumns = Object.entries(dataset.sample_schema)
    .filter(([, type]) => type === "text" || type === "sample_id")
    .map(([name]) => name);
  const column = numericColumns.includes(selection.column) ? selection.column : numericColumns[0] ?? "";
  const compare = numericColumns.includes(selection.compare) && selection.compare !== column
    ? selection.compare
    : numericColumns.find((item) => item !== column) ?? "";
  const groupBy = groupColumns.includes(selection.groupBy) ? selection.groupBy : groupColumns[0] ?? "";
  return { column, compare, groupBy };
}

export function sourceRefLabel(ref: SourceRowRef): string {
  return `源文件第 ${ref.row_number} 行 · ${ref.column_name}`;
}

export function sortAnalysesByCreatedAt(items: AnalysisResult[]): AnalysisResult[] {
  return items.slice().sort((left, right) => right.created_at - left.created_at);
}

export function findSourceRow(
  dataset: ExperimentDataset | null,
  ref: SourceRowRef,
): ExperimentDataset["rows"][number] | null {
  return dataset?.rows.find((row) => row.row_number === ref.row_number) ?? null;
}

export function sourceRefsForPage(
  items: SourceRowRef[],
  page: number,
  pageSize = 12,
): SourceRowRef[] {
  const safePage = Math.max(0, Math.floor(page));
  const safePageSize = Math.max(1, Math.floor(pageSize));
  return items.slice(safePage * safePageSize, (safePage + 1) * safePageSize);
}

export function verificationLabel(status: SourceRowRef["verification_status"]): string {
  switch (status) {
    case "verified": return "来源已校验";
    case "fixture": return "演示来源";
    case "unavailable": return "来源暂不可用";
    default: return "来源待校验";
  }
}

export function operationLabel(operation: string): string {
  return OPERATION_LABELS[operation as AnalysisOperation] ?? operation;
}

export function displayResultValue(value: unknown): string {
  if (value === null || value === undefined) return "暂无";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "暂无";
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
