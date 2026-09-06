"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { MeetingEvent, RunStep } from "@/lib/api";
import { MessageFeed } from "@/components/run/message-feed";
import { PhaseIndicator } from "@/components/run/phase-indicator";
import { useRunStore } from "@/lib/stores/run-store";
import { ChainView } from "./chain-view";
import { AgentLane } from "@/components/run/agent-lane";
import { RuntimeEventFeed } from "@/components/run/runtime-event-feed";

type Props = {
  steps: RunStep[];
  visibleSteps: number;
  phase: string;
  status: string;
  cycle: number;
  mode: string;
  meetingEvents: MeetingEvent[];
  runControls?: ReactNode;
  onMeetingEnd?: () => void;
};

export function ValueChainTabs({
  steps,
  visibleSteps,
  phase,
  status,
  cycle,
  mode,
  meetingEvents,
  runControls,
  onMeetingEnd,
}: Props) {
  const [tab, setTab] = useState<"feed" | "chain">("feed");
  const autoSwitchedRef = useRef(false);
  const runId = useRunStore((s) => s.runId);
  const agentSpecs = useRunStore((s) => s.snapshot?.agent_specs ?? []);
  const agentStates = useRunStore((s) => s.agentStates);
  const candidateByAgent = useRunStore((s) => s.candidateByAgent);
  const runtimeEvents = useRunStore((s) => s.runtimeEvents);

  // awaiting_decision 时自动切到价值链（仅一次；之后尊重用户选择）。
  useEffect(() => {
    if (
      (status === "awaiting_decision" || status === "failed") &&
      !autoSwitchedRef.current
    ) {
      autoSwitchedRef.current = true;
      setTab("chain");
    }
  }, [status]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b px-4 py-3">
        <div className="inline-flex rounded-md border bg-muted/40 p-0.5">
          {(
            [
              { value: "feed", label: "消息流" },
              { value: "chain", label: "价值链" },
            ] as const
          ).map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => setTab(t.value)}
              className={cn(
                "rounded px-3 py-1 text-xs font-medium transition-colors",
                tab === t.value
                  ? "bg-secondary text-secondary-foreground shadow"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <PhaseIndicator phase={phase} cycle={cycle} status={status} mode={mode} />
        {runControls}
      </div>
      <AgentLane agents={agentSpecs} states={agentStates} />
      <RuntimeEventFeed events={runtimeEvents} candidateByAgent={candidateByAgent} />
      {tab === "feed" ? (
        <MessageFeed
          steps={steps}
          visibleCount={visibleSteps}
          hideNonMeetingDialogue={phase !== "meeting"}
        />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ChainView
            steps={steps}
            visibleSteps={visibleSteps}
            phase={phase}
            status={status}
            runId={runId ?? ""}
            meetingEvents={meetingEvents}
            onMeetingEnd={onMeetingEnd}
          />
        </div>
      )}
    </div>
  );
}
