/**
 * 价值链数据分组提取纯函数（design.md §4），零 React 依赖。
 * 过滤/配对规则基于 payload 实测断言（design.md §2）。
 */
import type { RunStep } from "@/lib/api";

const DEBATE_PHASES = new Set(["discussion", "review_triggered_debate"]);

/** phase=independent_analysis, kind=claim → 冻结观点卡片数据。 */
export function frozenClaims(steps: RunStep[]): RunStep[] {
  return steps.filter((s) => s.phase === "independent_analysis" && s.kind === "claim");
}

/** kind=turn 且 phase ∈ {discussion, review_triggered_debate} → 辩论链（按出现顺序）。 */
export function debateTurns(steps: RunStep[]): RunStep[] {
  return steps.filter((s) => s.kind === "turn" && DEBATE_PHASES.has(s.phase));
}

export type ReviewItem = {
  opinion: RunStep;
  dispositions: RunStep[];
};

/** review_gate 的 review_opinion + 其后 revision 阶段 disposition 配对。 */
export function reviewItems(steps: RunStep[]): ReviewItem[] {
  const items: ReviewItem[] = [];
  let current: ReviewItem | null = null;
  for (const step of steps) {
    if (step.phase === "review_gate" && step.kind === "review_opinion") {
      current = { opinion: step, dispositions: [] };
      items.push(current);
    } else if (step.phase === "revision" && step.kind === "disposition") {
      if (current !== null) {
        current.dispositions.push(step);
      }
    }
  }
  return items;
}

export type MeetingData = {
  agenda: RunStep[];
  unresolved: RunStep[];
  suggested: RunStep[];
  decision?: RunStep;
};

/** meeting 相关步骤分组。 */
export function meetingData(steps: RunStep[]): MeetingData {
  const agenda: RunStep[] = [];
  const unresolved: RunStep[] = [];
  const suggested: RunStep[] = [];
  let decision: RunStep | undefined;
  for (const step of steps) {
    if (step.kind === "agenda") agenda.push(step);
    else if (step.kind === "unresolved") unresolved.push(step);
    else if (step.kind === "suggested_decision") suggested.push(step);
    else if (step.kind === "decision") decision = step;
  }
  return { agenda, unresolved, suggested, decision };
}
