import { FileUp } from "lucide-react";
import { useRef } from "react";

export function DatasetUpload({
  disabled,
  loading,
  onFile,
}: {
  disabled?: boolean;
  loading?: boolean;
  onFile: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={inputRef}
        className="hidden"
        type="file"
        accept=".csv,.xlsx"
        aria-label="选择实验数据文件"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={disabled}
        className="inline-flex h-8 items-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-3 text-xs font-medium text-primary hover:bg-primary/20 disabled:opacity-50"
        onClick={() => inputRef.current?.click()}
      >
        <FileUp className="size-3.5" aria-hidden />
        {loading ? "正在预览…" : "上传 CSV / XLSX"}
      </button>
    </>
  );
}
