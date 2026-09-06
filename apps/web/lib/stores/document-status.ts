type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export type DocumentStatusMeta = {
  label: string;
  tone: "neutral" | "info" | "success" | "error";
};

const STATUS_META: Record<DocumentStatus, DocumentStatusMeta> = {
  uploaded: { label: "待索引", tone: "neutral" },
  processing: { label: "索引中", tone: "info" },
  ready: { label: "已就绪", tone: "success" },
  failed: { label: "索引失败", tone: "error" },
};

export function documentStatusMeta(status: DocumentStatus): DocumentStatusMeta {
  return STATUS_META[status];
}
