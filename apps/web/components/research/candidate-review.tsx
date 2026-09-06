"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, ExternalLink, LoaderCircle, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  approveCandidate,
  candidateEvidenceHref,
  listCandidates,
  rejectCandidate,
  type CandidateClaim,
  type CandidateEvidenceRef,
} from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import { useRunStore } from "@/lib/stores/run-store";
import { cn } from "@/lib/utils";
import {
  reduceCandidate,
  type CandidateReviewState,
} from "./candidate-review-state";

function readableError(error: unknown): string {
  if (error instanceof ApiError || error instanceof ApiConfigError) return error.message;
  return "审阅请求失败，请稍后重试";
}

function statusLabel(status: CandidateClaim["status"]): string {
  return status === "approved" ? "已批准" : status === "rejected" ? "已拒绝" : "候选";
}

function statusVariant(status: CandidateClaim["status"]): "success" | "destructive" | "warning" {
  return status === "approved" ? "success" : status === "rejected" ? "destructive" : "warning";
}

function sourceLabel(evidence: CandidateEvidenceRef): string {
  if (evidence.source_type === "experiment") {
    return `${evidence.source_filename ?? evidence.page_or_location} · 分析结果`;
  }
  if (evidence.source_type === "literature") return evidence.page_or_location;
  return `${evidence.page_or_location} · ${evidence.chunk_id ?? "文档来源"}`;
}

type CandidateReviewProps = {
  groupChatId: string;
  runId?: string | null;
  runStatus?: string;
  variant?: "panel" | "chat";
};

export function CandidateReview({
  groupChatId,
  runId: providedRunId,
  runStatus: providedRunStatus,
  variant = "panel",
}: CandidateReviewProps) {
  const activeRunId = useRunStore((state) => state.runId);
  const activeRunStatus = useRunStore((state) => state.snapshot?.status ?? "");
  const refreshRun = useRunStore((state) => state.refresh);
  const runId = providedRunId ?? activeRunId;
  const runStatus = providedRunStatus ?? activeRunStatus;
  const isChat = variant === "chat";
  const [candidates, setCandidates] = useState<CandidateClaim[]>([]);
  const [reviewStates, setReviewStates] = useState<Record<string, CandidateReviewState>>({});
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCandidates = useCallback(async () => {
    if (!runId) {
      setCandidates([]);
      return;
    }
    setLoading(true);
    try {
      const next = await listCandidates(runId);
      setCandidates(next);
      setReviewStates((current) => {
        const merged = { ...current };
        for (const candidate of next) {
          merged[candidate.candidate_id] ??= {
            status: candidate.status,
            busy: false,
            error: null,
          };
        }
        return merged;
      });
      setError(null);
    } catch (requestError) {
      setError(readableError(requestError));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates, runStatus]);

  const review = async (candidate: CandidateClaim, action: "approve" | "reject") => {
    if (!runId) return;
    const current = reviewStates[candidate.candidate_id] ?? {
      status: candidate.status,
      busy: false,
      error: null,
    };
    setReviewStates((state) => ({
      ...state,
      [candidate.candidate_id]: reduceCandidate(current, { type: "start" }),
    }));
    try {
      const next = action === "approve"
        ? await approveCandidate(runId, candidate.candidate_id)
        : await rejectCandidate(runId, candidate.candidate_id, reason);
      setCandidates((items) => items.map((item) =>
        item.candidate_id === next.candidate_id ? next : item,
      ));
      setReviewStates((state) => ({
        ...state,
        [candidate.candidate_id]: reduceCandidate(current, { type: action }),
      }));
      setReason("");
      await refreshRun();
    } catch (requestError) {
      setReviewStates((state) => ({
        ...state,
        [candidate.candidate_id]: reduceCandidate(current, {
          type: "error",
          message: readableError(requestError),
        }),
      }));
    }
  };

  return (
    <section
      className={cn(!isChat && "research-panel candidate-review", isChat && "space-y-3")}
      data-testid="candidate-review"
      aria-labelledby="candidate-review-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          {!isChat && <p className="eyebrow">Review gate</p>}
          <h2 id="candidate-review-title" className={cn("text-base font-semibold", !isChat && "mt-1")}>
            候选结论审阅
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            候选输出仅在批准后进入正式研究对象。
          </p>
        </div>
      </div>

      {loading && <p className="mt-4 text-sm text-muted-foreground">正在读取候选结果…</p>}
      {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      {!loading && candidates.length === 0 && (
        <div className="empty-state mt-4">Live Run 产出候选后，结果会出现在这里。</div>
      )}

      <div className={cn("mt-4 space-y-3", isChat && "mt-3")}>
        {candidates.map((candidate) => {
          const reviewState = reviewStates[candidate.candidate_id] ?? {
            status: candidate.status,
            busy: false,
            error: null,
          };
          const canReview = runStatus === "awaiting_review" && reviewState.status === "candidate";
          return (
            <article
              key={candidate.candidate_id}
              className={cn(
                !isChat && "candidate-item",
                isChat && "border-t border-border/70 pt-3 first:border-t-0 first:pt-0",
              )}
              data-testid="candidate-item"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="status-mark status-mark-amber" aria-hidden />
                  <span>候选结论</span>
                </div>
                <Badge variant={statusVariant(reviewState.status)}>{statusLabel(reviewState.status)}</Badge>
              </div>
              <h3 className="mt-3 text-sm font-medium leading-6 text-foreground">{candidate.claim}</h3>
              <div className={cn("mt-3 grid gap-3", !isChat && "md:grid-cols-3", isChat && "gap-2")}>
                <div>
                  <p className="field-label">依据摘要</p>
                  <p className="field-value">{candidate.reasoning_summary}</p>
                </div>
                <div>
                  <p className="field-label">不确定性</p>
                  <p className="field-value">{candidate.uncertainty}</p>
                </div>
                <div>
                  <p className="field-label">下一步</p>
                  <p className="field-value">{candidate.next_action}</p>
                </div>
              </div>
              <div className={cn("border-t border-border/70 pt-3", isChat ? "mt-3" : "mt-4")}>
                <p className="field-label">来源定位</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {candidate.evidence.map((evidence) => {
                    const href = candidateEvidenceHref(evidence, groupChatId);
                    const content = <>
                      {href && <ExternalLink className="size-3.5" />}
                      {sourceLabel(evidence)}
                    </>;
                    return href ? (
                      <a
                        key={evidence.source_ref}
                        className="source-link"
                        href={href}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {content}
                      </a>
                    ) : (
                      <span key={evidence.source_ref} className="source-link source-link-muted">
                        {content}
                      </span>
                    );
                  })}
                  {candidate.evidence.length === 0 && candidate.evidence_refs.map((ref) => (
                    <span key={ref} className="source-link source-link-muted">{ref}</span>
                  ))}
                </div>
              </div>
              {reviewState.error && <p className="mt-3 text-xs text-destructive">{reviewState.error}</p>}
              {canReview && (
                <div className={cn("flex flex-col gap-2 border-t border-border/70 pt-3 sm:flex-row sm:items-end", isChat ? "mt-3" : "mt-4")}>
                  <Textarea
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="拒绝时填写原因（可选）"
                    aria-label="拒绝原因"
                    className="min-h-9 flex-1 resize-none py-2 text-xs"
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={reviewState.busy}
                      onClick={() => void review(candidate, "reject")}
                    >
                      {reviewState.busy ? <LoaderCircle className="animate-spin" /> : <X />}
                      拒绝
                    </Button>
                    <Button
                      size="sm"
                      disabled={reviewState.busy}
                      onClick={() => void review(candidate, "approve")}
                    >
                      {reviewState.busy ? <LoaderCircle className="animate-spin" /> : <Check />}
                      批准
                    </Button>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
