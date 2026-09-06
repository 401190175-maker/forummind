"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { decide, type DecisionOption } from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import { useRunStore } from "@/lib/stores/run-store";
import { OPTION_LABELS } from "./meeting-panel";

type Props = {
  runId: string;
};

const OPTIONS: DecisionOption[] = [
  "approved",
  "approved_with_conditions",
  "returned",
  "deferred",
  "terminated",
];

export function PiDecision({ runId }: Props) {
  const [selected, setSelected] = useState<DecisionOption | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (selected === null || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await decide(runId, selected, reason.trim());
      await useRunStore.getState().refresh();
      setSelected(null);
      setReason("");
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "提交裁决失败，请重试",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-2 rounded-md border p-3">
      <p className="text-sm font-medium">PI 裁决</p>
      <div className="flex flex-wrap gap-1.5">
        {OPTIONS.map((opt) => (
          <button
            key={opt}
            type="button"
            disabled={submitting}
            onClick={() => setSelected(opt)}
            className={cn(
              "rounded border px-2.5 py-1 text-xs font-medium transition-colors",
              selected === opt
                ? "border-primary bg-primary/15 text-primary"
                : "border-input hover:bg-accent",
            )}
          >
            {OPTION_LABELS[opt]}
          </button>
        ))}
      </div>
      <Textarea
        rows={2}
        value={reason}
        placeholder="裁决理由（可选）"
        disabled={submitting}
        onChange={(e) => setReason(e.target.value)}
      />
      {error !== null && <p className="text-xs text-destructive">{error}</p>}
      <Button size="sm" className="w-full" onClick={() => void handleSubmit()} disabled={selected === null || submitting}>
        {submitting ? "提交中…" : "提交裁决"}
      </Button>
    </div>
  );
}
