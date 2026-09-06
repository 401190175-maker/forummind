"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import type { ExperimentPlanView } from "@/lib/api";

type Props = {
  plan: ExperimentPlanView | null;
};

function listOrDash(items: string[]) {
  if (items.length === 0) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <ul className="space-y-1">
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className="break-words">
          {item}
        </li>
      ))}
    </ul>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border bg-card p-3">
      <p className="mb-1 text-[11px] font-medium text-muted-foreground">{label}</p>
      <div className="text-sm leading-6">{children}</div>
    </div>
  );
}

export function ExperimentCard({ plan }: Props) {
  if (!plan) {
    return (
      <section className="rounded-md border bg-card p-4">
        <p className="text-sm font-medium">暂无判别实验方案</p>
        <p className="mt-1 text-xs text-muted-foreground">
          PI 批准后将在这里展示最小判别实验。
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3 rounded-md border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">{plan.title}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            synthetic demo 方案，仅用于展示判别路径。
          </p>
        </div>
        <Badge variant="outline">
          {plan.approval_boundary
            ? `PI ${plan.approval_boundary.option}`
            : "待 PI 批准"}
        </Badge>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Field label="候选解释">{listOrDash(plan.candidate_explanations)}</Field>
        <Field label="控制变量">{listOrDash(plan.controls)}</Field>
        <Field label="样品链">{plan.sample_chain || "—"}</Field>
        <Field label="测量指标">{listOrDash(plan.measurements)}</Field>
        <Field label="预期结果分支">{listOrDash(plan.branches)}</Field>
        <Field label="分支影响规则">{listOrDash(plan.branch_effects)}</Field>
        <Field label="资源成本与风险">{plan.cost_risk || "—"}</Field>
        <Field label="批准边界">
          {plan.approval_boundary ? (
            <div className="space-y-1">
              <p>{plan.approval_boundary.option}</p>
              <p className="text-muted-foreground">{plan.approval_boundary.reason}</p>
            </div>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </Field>
      </div>
    </section>
  );
}
