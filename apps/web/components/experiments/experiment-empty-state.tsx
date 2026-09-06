import { FlaskConical } from "lucide-react";

export function ExperimentEmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center border border-dashed border-border/80 px-5 text-center">
      <FlaskConical className="mb-3 size-7 text-primary" aria-hidden />
      <p className="text-sm font-medium">还没有实验数据集</p>
      <p className="mt-1 max-w-xs text-xs leading-5 text-muted-foreground">
        上传 CSV 或 XLSX，先预览字段，再导入一个可追溯的不可变版本。
      </p>
      <button
        type="button"
        className="mt-4 inline-flex h-8 items-center gap-2 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        onClick={onUpload}
      >
        上传实验数据
      </button>
    </div>
  );
}
