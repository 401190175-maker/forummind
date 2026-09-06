"use client";

import { Fragment, useEffect, useRef } from "react";
import Link from "next/link";

import type { RunStep } from "@/lib/api";
import { phaseLabel } from "./labels";
import { StepMessage } from "./step-message";

type Props = {
  steps: RunStep[];
  visibleCount: number;
  /** 日常状态下，Agent 之间的讨论不在课题组群聊播放。 */
  hideNonMeetingDialogue?: boolean;
};

export function MessageFeed({
  steps,
  visibleCount,
  hideNonMeetingDialogue = false,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleCount]);

  const visible = steps.slice(0, visibleCount);
  const suppressedPhases = new Set(["discussion", "review_triggered_debate"]);
  const renderedSuppressedPhases = new Set<string>();

  return (
    <div className="flex-1 space-y-2 overflow-y-auto px-4 py-4">
      {visibleCount === 0 && <p className="text-sm text-muted-foreground">团队启动中…</p>}
      {visible.map((step, i) => {
        const suppressed = hideNonMeetingDialogue && suppressedPhases.has(step.phase);
        if (suppressed) {
          if (renderedSuppressedPhases.has(step.phase)) return null;
          renderedSuppressedPhases.add(step.phase);
          return (
            <div key={`suppressed-${step.phase}`} className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
              {phaseLabel(step.phase)} 的 Agent 交互已转入
              <Link className="ml-1 text-primary underline underline-offset-2" href="/chatrooms">
                聊天室
              </Link>
              ，课题组群聊只保留任务状态和审阅产物。
            </div>
          );
        }
        const previousVisible = visible[i - 1];
        return (
          <Fragment key={step.id}>
            {previousVisible && previousVisible.phase !== step.phase && (
              <div className="flex items-center gap-2 py-1 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                <span>{phaseLabel(step.phase)}</span>
                <span className="h-px flex-1 bg-border" />
              </div>
            )}
            <StepMessage step={step} />
          </Fragment>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
