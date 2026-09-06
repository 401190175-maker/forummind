"use client";

import { FileText } from "lucide-react";

type Props = {
  content: string;
  payload: Record<string, unknown>;
};

function humanSize(bytes: unknown): string {
  const value = typeof bytes === "number" ? bytes : 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function statusLabel(status: unknown): string {
  if (status === "ready") return "资料已可检索";
  if (status === "failed") return "资料处理失败";
  if (status === "processing") return "资料正在处理";
  return "已上传";
}

/** 气泡内附件的紧凑渲染：文件名、类型/大小与人类可读的处理状态。 */
export function ChatAttachment({ content, payload }: Props) {
  const mimeType = typeof payload.mime_type === "string" ? payload.mime_type : "";
  const size = humanSize(payload.size_bytes);
  const meta = [mimeType, size].filter(Boolean).join(" · ") || "文件";

  return (
    <div className="flex items-start gap-2">
      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0">
        <p className="truncate font-medium">{content}</p>
        <p className="text-xs text-muted-foreground">{meta}</p>
        <p className="text-xs text-muted-foreground">{statusLabel(payload.status)}</p>
      </div>
    </div>
  );
}
