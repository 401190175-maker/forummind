"use client";

import { Play } from "lucide-react";

type Props = {
  payload: Record<string, unknown>;
  onStart: (clarificationId: string) => void;
  pending?: boolean;
};

/**
 * 澄清完成后的任务就绪消息：仅在 durable clarification_ready 载荷有效时
 * 暴露“开始分析”命令，绝不绕过服务端审批门。
 */
export function TaskReadyMessage({ payload, onStart, pending = false }: Props) {
  const clarificationId =
    typeof payload.clarification_id === "string" && payload.clarification_id
      ? payload.clarification_id
      : null;

  if (!clarificationId) return null;

  const datasetRefs = Array.isArray(payload.dataset_refs)
    ? payload.dataset_refs.filter((item): item is { version: number } => typeof item === "object" && item !== null && typeof (item as { version?: unknown }).version === "number")
    : [];
  const datasetLabels = Array.isArray(payload.dataset_labels)
    ? payload.dataset_labels.filter((item): item is string => typeof item === "string")
    : [];

  return (
    <div className="space-y-2">
      <p>任务已确认，可以开始分析课题组资料。</p>
      {datasetRefs.length > 0 && (
        <p className="text-xs text-muted-foreground">
          已绑定 {datasetRefs.length} 个实验数据版本：{datasetRefs.map((ref, index) => datasetLabels[index] ?? `实验数据版本 v${ref.version}`).join("、")}
        </p>
      )}
      <button
        type="button"
        disabled={pending}
        aria-busy={pending}
        onClick={() => onStart(clarificationId)}
        className="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
      >
        <Play className="h-4 w-4" aria-hidden />
        {pending ? "启动中…" : "开始分析"}
      </button>
    </div>
  );
}
