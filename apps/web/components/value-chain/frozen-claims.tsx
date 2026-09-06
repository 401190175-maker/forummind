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

type Props = {
  claims: RunStep[];
};

type ClaimPayload = {
  capability?: unknown;
  boundary?: unknown;
  prediction?: unknown;
  falsification_condition?: unknown;
};

function text(value: unknown): string {
  return typeof value === "string" && value.length > 0 ? value : "—";
}

export function FrozenClaims({ claims }: Props) {
  if (claims.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">暂无冻结观点。</p>;
  }
  return (
    <div className="grid gap-4 p-4 md:grid-cols-3">
      {claims.map((claim) => {
        const payload = (claim.payload ?? {}) as ClaimPayload;
        return (
          <Card key={claim.id}>
            <CardHeader className="space-y-2">
              <Badge variant="secondary" className="w-fit">
                {actorLabel(claim.actor)}
              </Badge>
              <CardTitle className="text-sm leading-relaxed">{claim.content}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="font-medium">适用边界：</span>
                <span className="text-muted-foreground">{text(payload.boundary)}</span>
              </p>
              <p>
                <span className="font-medium">预测：</span>
                <span className="text-muted-foreground">{text(payload.prediction)}</span>
              </p>
              <p>
                <span className="font-medium">可推翻条件：</span>
                <span className="text-muted-foreground">
                  {text(payload.falsification_condition)}
                </span>
              </p>
              <Badge variant="outline">{text(payload.capability)}</Badge>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
