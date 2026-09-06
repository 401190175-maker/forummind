"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RunStep } from "@/lib/api";
import { actorLabel, kindMeta, phaseLabel, type KindTone } from "./labels";

type Props = {
  step: RunStep;
};

const TONE_BORDER: Record<KindTone, string> = {
  primary: "border-primary/40",
  warning: "border-warning/40",
  success: "border-ok/40",
  secondary: "border-border",
  muted: "border-border",
};

export function StepMessage({ step }: Props) {
  const meta = kindMeta(step.kind);
  const hasPayload = step.payload !== null && step.payload !== undefined;

  return (
    <div className={cn("rounded-md border px-3 py-2", TONE_BORDER[meta.tone])}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant={meta.tone === "primary" ? "default" : meta.tone === "success" ? "success" : meta.tone === "warning" ? "warning" : "secondary"}>
          {meta.icon} {meta.label}
        </Badge>
        <span className="font-medium text-foreground">{actorLabel(step.actor)}</span>
        <span>{phaseLabel(step.phase)}</span>
      </div>
      <p className="mt-1 text-sm">{step.content}</p>
      {hasPayload && (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs text-muted-foreground">详情 ▾</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-muted/40 p-2 text-xs text-muted-foreground">
            {JSON.stringify(step.payload, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
