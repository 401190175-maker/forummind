"use client";

import type { MeetingEvent, RunStep } from "@/lib/api";
import { MessageFeed } from "@/components/run/message-feed";
import { debateTurns, frozenClaims, meetingData, reviewItems } from "./selectors";
import { FrozenClaims } from "./frozen-claims";
import { DebateChain } from "./debate-chain";
import { ReviewGate } from "./review-gate";
import { MeetingPanel } from "./meeting-panel";
import { ExperimentView } from "./experiment-view";

type Props = {
  steps: RunStep[];
  visibleSteps: number;
  phase: string;
  status: string;
  runId: string;
  meetingEvents: MeetingEvent[];
  onMeetingEnd?: () => void;
};

/** 价值链区块映射（design.md §5.3）。 */
export function ChainView({
  steps,
  visibleSteps,
  phase,
  status,
  runId,
  meetingEvents,
  onMeetingEnd,
}: Props) {
  if (phase === "independent_analysis") {
    return <FrozenClaims claims={frozenClaims(steps)} />;
  }
  if (phase === "discussion" || phase === "review_triggered_debate") {
    return <DebateChain turns={debateTurns(steps)} />;
  }
  if (phase === "review_gate") {
    return <ReviewGate items={reviewItems(steps)} />;
  }
  if (phase === "meeting" || status === "failed") {
    return (
      <div className="flex h-full min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <MessageFeed steps={steps} visibleCount={visibleSteps} />
        </div>
        <MeetingPanel
          data={meetingData(steps)}
          events={meetingEvents}
          awaiting={status === "awaiting_decision"}
          runId={runId}
          onMeetingEnd={phase === "meeting" ? onMeetingEnd : undefined}
        />
      </div>
    );
  }
  if (
    phase === "discriminating_experiment" ||
    phase === "data_import" ||
    phase === "conclusion"
  ) {
    return <ExperimentView />;
  }
  return (
    <div className="p-4">
      <p className="text-sm text-muted-foreground">该阶段暂无结构化视图，请查看消息流。</p>
    </div>
  );
}
