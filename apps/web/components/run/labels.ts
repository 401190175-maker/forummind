/**
 * phase / kind / actor 中文映射纯函数（design.md §9），零 React 依赖。
 * 未知值一律兜底返回原值，保证不因映射遗漏而崩溃。
 */

export type KindTone = "primary" | "muted" | "success" | "warning" | "secondary";

/* ------------------------------ phase ------------------------------ */

const PHASE_LABELS: Record<string, string> = {
  independent_analysis: "独立分析",
  discussion: "自由讨论",
  review_gate: "审查门",
  review_triggered_debate: "触发辩论",
  revision: "逐条处置修订",
  freeze: "冻结（组会前一小时）",
  meeting: "组会",
  postdoc_exchange: "专业请求",
  discriminating_experiment: "判别实验",
  data_import: "数据导入",
  conclusion: "结论",
};

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase;
}

/* ------------------------------ kind ------------------------------- */

const KIND_META: Record<string, { label: string; icon: string; tone: KindTone }> = {
  claim: { label: "观点", icon: "💡", tone: "primary" },
  debate_turn: { label: "辩论", icon: "⚔️", tone: "warning" },
  review_opinion: { label: "审查意见", icon: "🔍", tone: "secondary" },
  disposition: { label: "处置", icon: "✍️", tone: "secondary" },
  agenda: { label: "议程", icon: "📋", tone: "secondary" },
  decision: { label: "PI 裁决", icon: "🏛️", tone: "success" },
  freeze: { label: "冻结", icon: "❄️", tone: "secondary" },
  results: { label: "结果", icon: "📊", tone: "secondary" },
  postdoc_exchange: { label: "专业请求", icon: "🎓", tone: "secondary" },
  session: { label: "讨论会话", icon: "💬", tone: "secondary" },
  turn: { label: "发言轮次", icon: "🗣️", tone: "secondary" },
  request: { label: "专业请求", icon: "🎓", tone: "secondary" },
  in_scope_answer: { label: "范围内回答", icon: "✅", tone: "success" },
  out_of_scope_refusal: { label: "范围外拒答", icon: "⛔", tone: "warning" },
  unresolved: { label: "未决分歧", icon: "⚠️", tone: "warning" },
  suggested_decision: { label: "建议裁决", icon: "📝", tone: "secondary" },
  system: { label: "系统", icon: "ℹ️", tone: "muted" },
};

export function kindMeta(kind: string): { label: string; icon: string; tone: KindTone } {
  return KIND_META[kind] ?? { label: kind, icon: "ℹ️", tone: "muted" };
}

/* ------------------------------ actor ------------------------------ */

const ACTOR_LABELS: Record<string, string> = {
  "agent-ms-1": "硕士 A",
  "agent-ms-2": "硕士 B",
  "agent-ms-3": "硕士 C",
  "agent-phd-1": "博士",
  "agent-postdoc-1": "博后",
  "agent-secretary-1": "组会秘书",
  PI: "PI",
  system: "系统",
};

export function actorLabel(actor: string): string {
  return ACTOR_LABELS[actor] ?? actor;
}

/* ------------------------------ role ------------------------------- */

const ROLE_LABELS: Record<string, string> = {
  master_student: "硕士",
  phd_student: "博士",
  postdoc: "博士后",
  group_meeting_secretary: "组会秘书",
};

/** AgentProfile.role → 中文展示名；未知兜底原值。 */
export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}
