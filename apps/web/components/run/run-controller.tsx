"use client";

import { Badge } from "@/components/ui/badge";
import { useRunStore } from "@/lib/stores/run-store";
import type { RunMode } from "@/lib/api";

type Props = {
  teamActive: boolean;
  mode: RunMode;
  onModeChange: (mode: RunMode) => void;
  onToggleTeam: (active: boolean) => void;
};

/**
 * Live-only 浏览器边界：不再渲染模式选择器、团队开关，也不显示任何由
 * snapshot.mode、runtime_name 或原始状态码派生的标签。仅保留面向用户的
 * 运行状态与错误提示（team/mode props 仅供 Task 8 之前的页面兼容）。
 */
export function RunController(_props: Props) {
  const polling = useRunStore((s) => s.polling);
  const error = useRunStore((s) => s.error);

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2">
        {polling === "stopped" && <Badge variant="success">运行结束</Badge>}
        {polling === "failed" && <Badge variant="destructive">运行失败</Badge>}
        {polling === "error" && <Badge variant="destructive">运行出错</Badge>}
      </div>
      {error !== null && (
        <p className="max-w-md text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}
