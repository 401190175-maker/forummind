"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { actorLabel } from "@/components/run/labels";
import type { RunStep } from "@/lib/api";
import type { ReviewItem } from "./selectors";

type Props = {
  items: ReviewItem[];
};

const DISPOSITION_LABELS: Record<string, string> = {
  accepted: "接受",
  rejected: "拒绝",
};

type DispositionPayload = {
  disposition?: unknown;
  reason?: unknown;
};

function dispositionVariant(disposition: unknown) {
  if (disposition === "accepted") return "success" as const;
  if (disposition === "rejected") return "destructive" as const;
  return "secondary" as const;
}

export function ReviewGate({ items }: Props) {
  if (items.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">暂无审查意见。</p>;
  }
  return (
    <div className="space-y-4 p-4">
      {items.map(({ opinion, dispositions }) => (
        <Card key={opinion.id}>
          <CardHeader className="space-y-2">
            <Badge variant="secondary" className="w-fit">
              博士审查意见
            </Badge>
            <CardTitle className="text-sm leading-relaxed">{opinion.content}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {dispositions.length === 0 && (
              <p className="text-xs text-muted-foreground">（无逐条处置记录）</p>
            )}
            {dispositions.map((d) => {
              const payload = (d.payload ?? {}) as DispositionPayload;
              const disposition = payload.disposition;
              const reason =
                typeof payload.reason === "string" && payload.reason.length > 0
                  ? payload.reason
                  : null;
              return (
                <div key={d.id} className="flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
                  <Badge variant={dispositionVariant(disposition)} className="shrink-0">
                    {DISPOSITION_LABELS[disposition as string] ??
                      (typeof disposition === "string" ? disposition : "—")}
                  </Badge>
                  <div className="min-w-0">
                    <span className="font-medium">{actorLabel(d.actor)}</span>
                    <span className="ml-2 text-muted-foreground">{d.content}</span>
                    {reason !== null && <p className="mt-0.5 text-xs text-muted-foreground">{reason}</p>}
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
