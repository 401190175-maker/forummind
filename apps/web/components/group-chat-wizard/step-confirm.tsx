"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AgentInfoCard } from "@/components/agent-info-card";
import type { AgentProfile } from "@/lib/api";
import { roleCount } from "./validation";
import type { RoleKey, WizardDraft } from "./types";

type Props = {
  draft: WizardDraft;
  agents: AgentProfile[] | null;
  submitting: boolean;
  error: string | null;
  onCreate: () => void;
  onBack: () => void;
  onCancel: () => void;
};

const ROLE_LABELS: Record<RoleKey, string> = {
  postdoc: "博士后",
  phd_student: "博士",
  master_student: "硕士",
};

function agentDisplayName(agentId: string, agents: AgentProfile[] | null): string {
  const found = agents?.find((a) => a.agent_id === agentId);
  return found ? `${found.name}（${agentId}）` : agentId;
}

export function StepConfirm({ draft, agents, submitting, error, onCreate, onBack, onCancel }: Props) {
  const [showMembers, setShowMembers] = useState<RoleKey | null>(null);
  const roleEntries = (Object.keys(ROLE_LABELS) as RoleKey[]).map((roleKey) => {
    const selection = draft.memberSelection[roleKey];
    const detail =
      selection.mode === "generate"
        ? `智能生成 ×${selection.count}`
        : selection.agentIds.map((id) => agentDisplayName(id, agents)).join("、") || "（未选择）";
    return {
      roleKey,
      label: ROLE_LABELS[roleKey],
      detail,
      count: roleCount(selection),
      agentIds: selection.mode === "existing" ? selection.agentIds : [],
      generateProfiles: selection.mode === "generate" ? selection.generateProfiles : [],
    };
  });

  const findAgent = (agentId: string): AgentProfile | undefined =>
    agents?.find((a) => a.agent_id === agentId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>信息确认</CardTitle>
        <CardDescription>确认课题信息与成员配置后创建课题组。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <p className="text-sm font-medium">课题名称</p>
          <p className="text-sm text-muted-foreground">{draft.topicName}</p>
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium">课题概述</p>
          <p className="text-sm text-muted-foreground">{draft.topicSummary}</p>
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">成员配置</p>
          {roleEntries.map((entry) => {
            const open = showMembers === entry.roleKey;
            return (
              <div key={entry.roleKey} className="space-y-1">
                <div className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                  <span className="text-muted-foreground">{entry.label}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-right">
                      {entry.detail}
                      <span className="ml-2 text-xs text-muted-foreground">（{entry.count} 人）</span>
                    </span>
                    {entry.agentIds.length > 0 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={submitting}
                        onClick={() => setShowMembers(open ? null : entry.roleKey)}
                      >
                        {open ? "收起" : "查看成员信息"}
                      </Button>
                    )}
                    {entry.generateProfiles.length > 0 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={submitting}
                        onClick={() => setShowMembers(open ? null : entry.roleKey)}
                      >
                        {open ? "收起" : "查看生成配置"}
                      </Button>
                    )}
                  </span>
                </div>
                {open && entry.agentIds.length > 0 &&
                  entry.agentIds.map((agentId) => {
                    const agent = findAgent(agentId);
                    return agent ? (
                      <AgentInfoCard key={agentId} agent={agent} />
                    ) : (
                      <p key={agentId} className="px-3 text-xs text-muted-foreground">
                        {agentId}（信息不可用）
                      </p>
                    );
                  })}
                {open && entry.generateProfiles.length > 0 &&
                  entry.generateProfiles.map((p, i) => (
                    <div key={i} className="space-y-1 rounded-md border bg-muted/20 p-3 text-sm">
                      <p>
                        <span className="font-medium">
                          {p.display_name || `待生成槽位 ${i + 1}`}
                        </span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {p.primary_ability ?? ""}
                        </span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        描述：{p.description || "—"} · Skills：{(p.general_research_abilities ?? []).join("、") || "—"}
                      </p>
                    </div>
                  ))}
              </div>
            );
          })}
        </div>
        {error !== null && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
      </CardContent>
      <CardFooter className="justify-between">
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={submitting}>
            取消
          </Button>
          <Button variant="outline" onClick={onBack} disabled={submitting}>
            上一步
          </Button>
        </div>
        <Button onClick={onCreate} disabled={submitting}>
          {submitting ? "创建中…" : "创建课题组"}
        </Button>
      </CardFooter>
    </Card>
  );
}
