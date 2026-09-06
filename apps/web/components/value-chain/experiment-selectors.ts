import type {
  DecisionOption,
  ExperimentPlanView,
  ExperimentResultsView,
  ExperimentView,
  HypothesisUpdateView,
  MemoryEntry,
  ResearchStateChangeView,
  RunSnapshot,
  RunStep,
} from "@/lib/api";

const BOUNDARY_NOTES = [
  "synthetic demo 数据不是真实实验结果。",
  "AI 不执行真实实验，只记录和展示演示实验设计与结果。",
  "符合预测不等于证明因果，支持程度变化仍需独立验证。",
  "后验解释必须标记为后验，不能倒写为预注册结论。",
];

function objectPayload(value: unknown): Record<string, unknown> {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function stringValue(value: unknown, fallback = "—"): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function rowsValue(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    : [];
}

function decisionOption(value: unknown): DecisionOption | null {
  return value === "approved" ||
    value === "approved_with_conditions" ||
    value === "returned" ||
    value === "deferred" ||
    value === "terminated"
    ? value
    : null;
}

function latestStep(steps: RunStep[], phase: string, kind: string): RunStep | null {
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const step = steps[index];
    if (step.phase === phase && step.kind === kind) {
      return step;
    }
  }
  return null;
}

function planFromSteps(steps: RunStep[]): ExperimentPlanView | null {
  const step = latestStep(steps, "discriminating_experiment", "plan");
  if (!step) return null;
  const payload = objectPayload(step.payload);
  const decision = latestStep(steps, "meeting", "decision");
  const decisionPayload = objectPayload(decision?.payload);
  const option = decisionOption(decisionPayload.option);
  const reason = stringValue(decisionPayload.reason, "");
  return {
    title: step.content || "最小判别实验方案",
    candidate_explanations: stringList(payload.candidate_explanations),
    controls: stringList(payload.controls),
    sample_chain: stringValue(payload.sample_chain),
    measurements: stringList(payload.measurements),
    branches: stringList(payload.branches),
    branch_effects: stringList(payload.branch_effects),
    cost_risk: stringValue(payload.cost_risk),
    approval_boundary: option && reason ? { option, reason } : null,
  };
}

function resultsFromSteps(steps: RunStep[]): ExperimentResultsView | null {
  const step = latestStep(steps, "data_import", "results");
  if (!step) return null;
  const payload = objectPayload(step.payload);
  return {
    source: stringValue(payload.source),
    rows: rowsValue(payload.rows),
    notes: stringValue(payload.notes),
    validation_summary: stringValue(payload.validation_summary),
    imported_at: typeof step.timestamp === "number" ? step.timestamp : null,
  };
}

function updatesFromSteps(steps: RunStep[]): HypothesisUpdateView[] {
  return steps
    .filter((step) => step.phase === "data_import" && step.kind === "hypothesis_update")
    .map((step) => {
      const payload = objectPayload(step.payload);
      return {
        claim_id: stringValue(payload.claim_id),
        status: stringValue(payload.status, "inconclusive"),
        reason: stringValue(payload.reason),
        causal_boundary: "支持程度变化不等于因果证明",
      };
    });
}

function researchStateChangeFromMemory(
  memory: MemoryEntry[],
  steps: RunStep[],
): ResearchStateChangeView | null {
  const states = memory.filter((entry) => entry.kind === "ResearchState");
  const conclusion = latestStep(steps, "conclusion", "conclusion");
  const importTriggeredState = [...states]
    .reverse()
    .find((entry) => objectPayload(entry.payload).trigger === "demo_experiment_result_import");
  if (states.length === 0) {
    if (!conclusion) return null;
    return null;
  }
  if (!importTriggeredState) return null;
  const current = importTriggeredState;
  const payload = objectPayload(current.payload);
  return {
    previous_ref: current.supersedes,
    current_ref: current.id,
    summary: stringValue(payload.summary),
    trigger: stringValue(payload.trigger),
    supersedes: current.supersedes !== null,
    preserves_old_version: true,
  };
}

export function experimentViewFromSnapshot(
  snapshot: Pick<RunSnapshot, "phase" | "steps" | "memory">,
): ExperimentView {
  return {
    data_space: "synthetic",
    phase: snapshot.phase,
    plan: planFromSteps(snapshot.steps),
    results: resultsFromSteps(snapshot.steps),
    hypothesis_updates: updatesFromSteps(snapshot.steps),
    research_state_change: resultsFromSteps(snapshot.steps)
      ? researchStateChangeFromMemory(snapshot.memory, snapshot.steps)
      : null,
    boundary_notes: BOUNDARY_NOTES,
  };
}
