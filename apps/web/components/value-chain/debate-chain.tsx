"use client";

import { Badge } from "@/components/ui/badge";
import { actorLabel } from "@/components/run/labels";
import type { RunStep } from "@/lib/api";

type Props = {
  turns: RunStep[];
};

const SEAT_LABELS: Record<string, string> = {
  proposal_owner: "方案提出者",
  discriminability: "判别力检查",
  feasibility_evidence: "可行性与证据检查",
};

type TurnPayload = {
  seat?: unknown;
};

export function DebateChain({ turns }: Props) {
  if (turns.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">暂无辩论记录。</p>;
  }
  return (
    <div className="space-y-0 p-4">
      {turns.map((turn) => {
        const seat = (turn.payload as TurnPayload | null)?.seat;
        return (
          <div key={turn.id} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className="mt-1.5 size-2 shrink-0 rounded-full bg-muted-foreground/50" />
              <span className="w-px flex-1 bg-border" />
            </div>
            <div className="mb-3 min-w-0 flex-1 rounded-md border px-3 py-2">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="secondary">{actorLabel(turn.actor)}</Badge>
                {typeof seat === "string" && seat.length > 0 && (
                  <Badge variant="warning">{SEAT_LABELS[seat] ?? seat}</Badge>
                )}
              </div>
              <p className="mt-1 text-sm">{turn.content}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
