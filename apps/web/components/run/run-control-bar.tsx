"use client";

import { LoaderCircle, Pause, Play, RefreshCw, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRunStore } from "@/lib/stores/run-store";

export function RunControlBar() {
  const runId = useRunStore((state) => state.runId);
  const polling = useRunStore((state) => state.polling);
  const connectionState = useRunStore((state) => state.connectionState);
  const snapshot = useRunStore((state) => state.snapshot);
  const control = useRunStore((state) => state.control);
  const busy = polling === "starting";
  const terminal = snapshot !== null && ["completed", "conclusion", "terminated", "cycle_exhausted", "failed"].includes(snapshot.status);
  if (!runId) return null;
  return (
    <div className="flex items-center gap-1">
      <Button size="icon" variant="ghost" title="暂停运行" aria-label="暂停运行" disabled={busy || terminal} onClick={() => void control("pause")}>
        <Pause />
      </Button>
      <Button size="icon" variant="ghost" title="继续运行" aria-label="继续运行" disabled={busy || terminal} onClick={() => void control("resume")}>
        <Play />
      </Button>
      <Button size="icon" variant="ghost" title="中止运行" aria-label="中止运行" disabled={busy || terminal} onClick={() => void control("abort")}>
        <Square />
      </Button>
      <Button size="icon" variant="ghost" title="重试当前 Agent" aria-label="重试当前 Agent" disabled={busy} onClick={() => void control("retry")}>
        <RefreshCw />
      </Button>
      <span className="sr-only">{connectionState === "reconnecting" ? "正在重新连接" : connectionState === "connected" ? "已连接" : "连接已关闭"}</span>
      {connectionState === "reconnecting" && <LoaderCircle className="size-4 animate-spin text-muted-foreground" aria-label="正在重新连接" />}
    </div>
  );
}
