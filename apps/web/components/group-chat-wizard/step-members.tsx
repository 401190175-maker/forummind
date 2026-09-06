"use client";

import { useState } from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
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
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import type { AgentRecord, GenerateProfile } from "@/lib/api";
import { MIN_ROLE_COUNTS, roleCount, validateStructure } from "./validation";
import type { RoleDraft, RoleKey, WizardDraft } from "./types";
import { GenerateProfileEditor, createDefaultProfiles, resizeProfiles } from "./generate-profiles";

export type CreateAgentDraft = {
  agentId: string;
  name: string;
  primaryAbility: string;
};

type Props = {
  draft: WizardDraft;
  agents: AgentRecord[] | null;
  agentsError: string | null;
  creatingAgentRole: RoleKey | null;
  testingAgentId: string | null;
  agentActionError: string | null;
  onReloadAgents: () => void;
  onCreateAgent: (role: RoleKey, profile: CreateAgentDraft) => void;
  onTestAgent: (agentId: string) => void;
  onChange: (patch: Partial<WizardDraft>) => void;
  onNext: () => void;
  onBack: () => void;
  onCancel: () => void;
};

function testStatusLabel(agent: AgentRecord): string {
  if (agent.latest_test === null) return "未测试";
  if (agent.latest_test.status === "ready") return "测试通过";
  if (agent.latest_test.status === "unavailable") return "Pi 不可用";
  return "测试失败";
}

function testStatusVariant(
  agent: AgentRecord,
): "outline" | "success" | "warning" | "destructive" {
  if (agent.latest_test === null) return "outline";
  if (agent.latest_test.status === "ready") return "success";
  if (agent.latest_test.status === "unavailable") return "warning";
  return "destructive";
}

/** 待生成槽位卡片：预览（只读摘要）+ 编辑（GenerateProfileEditor）。 */
function SlotCard({
  index,
  profile,
  roleKey,
  onProfileChange,
}: {
  index: number;
  profile: GenerateProfile;
  roleKey: RoleKey;
  onProfileChange: (p: GenerateProfile) => void;
}) {
  const [view, setView] = useState<"none" | "preview" | "edit">("none");
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
        <span>
          <span className="font-medium">
            {profile.display_name || `待生成槽位 ${index + 1}`}
          </span>
          <span className="ml-2 text-xs text-muted-foreground">
            {profile.primary_ability ?? ""}
          </span>
        </span>
        <div className="flex gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setView(view === "preview" ? "none" : "preview")}
          >
            {view === "preview" ? "收起预览" : "预览"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setView(view === "edit" ? "none" : "edit")}
          >
            {view === "edit" ? "收起编辑" : "编辑"}
          </Button>
        </div>
      </div>
      {view === "preview" && (
        <div className="space-y-1 rounded-md border bg-muted/20 p-3 text-sm">
          <p>
            <span className="font-medium">名称：</span>
            {profile.display_name || "—"}
          </p>
          <p>
            <span className="font-medium">主能力：</span>
            {profile.primary_ability || "—"}
          </p>
          <p>
            <span className="font-medium">描述：</span>
            {profile.description || "—"}
          </p>
          <p>
            <span className="font-medium">Skills：</span>
            {(profile.general_research_abilities ?? []).join("、") || "—"}
          </p>
          <p>
            <span className="font-medium">Tools：</span>
            {(profile.allowed_tools ?? []).join("、") || "文件 + 搜索（默认）"}
          </p>
        </div>
      )}
      {view === "edit" && (
        <GenerateProfileEditor profile={profile} onChange={onProfileChange} />
      )}
    </div>
  );
}

const ROLE_META: Record<
  RoleKey,
  {
    label: string;
    countLabel: string;
    minCount: number;
    maxCount: number;
    roleValue: string;
    responsibility: string;
    boundary: string;
  }
> = {
  postdoc: {
    label: "博士后",
    countLabel: "博后 ≥1",
    minCount: 1,
    maxCount: 2,
    roleValue: "postdoc",
    responsibility: "博士后：唯一接入受治理垂直领域知识库，在专业范围内参与讨论并独立科学审核。",
    boundary: "输出领域回答、审核意见、限制、反例和阶段建议；超出专业范围必须明确拒答，不批准重大实验或结论。",
  },
  phd_student: {
    label: "博士",
    countLabel: "博士 ≥1",
    minCount: 1,
    maxCount: 2,
    roleValue: "phd_student",
    responsibility: "博士：承担课题唯一整合责任，组织研究问题、竞争性解释、证据缺口、辩论与组会议程。",
    boundary: "博士负责汇总判别实验方案和更新研究状态，但不替导师批准重大阶段迁移、真实实验或重大结论。",
  },
  master_student: {
    label: "硕士",
    countLabel: "硕士 ≥3",
    minCount: 1,
    maxCount: 5,
    roleValue: "master_student",
    responsibility: "硕士：具有长期科研身份的独立研究者，开展机制探索、文献研究、实验设计、数据分析和科研写作。",
    boundary: "输出候选假设、分析草案、质疑与预测、成果初稿和自查清单；不批准实验或正式结论。",
  },
};

function RoleSection({
  roleKey,
  draft,
  roleAgents,
  agentsLoading,
  agentsError,
  creatingAgentRole,
  testingAgentId,
  onReloadAgents,
  onCreateAgent,
  onTestAgent,
  onChangeRole,
  structureOk,
}: {
  roleKey: RoleKey;
  draft: RoleDraft;
  roleAgents: AgentRecord[];
  agentsLoading: boolean;
  agentsError: string | null;
  creatingAgentRole: RoleKey | null;
  testingAgentId: string | null;
  onReloadAgents: () => void;
  onCreateAgent: (role: RoleKey, profile: CreateAgentDraft) => void;
  onTestAgent: (agentId: string) => void;
  onChangeRole: (patch: Partial<RoleDraft>) => void;
  structureOk: boolean;
}) {
  const meta = ROLE_META[roleKey];
  const current = roleCount(draft);
  const required = MIN_ROLE_COUNTS[roleKey];
  const missing = current < required;
  const [detailAgentId, setDetailAgentId] = useState<string | null>(null);
  const [createFormOpen, setCreateFormOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState<CreateAgentDraft>({
    agentId: "",
    name: "",
    primaryAbility: "",
  });
  const [createError, setCreateError] = useState<string | null>(null);

  const updateCreateDraft = (patch: Partial<CreateAgentDraft>) => {
    setCreateDraft((current) => ({ ...current, ...patch }));
    if (createError !== null) setCreateError(null);
  };

  const submitCreateAgent = () => {
    const profile = {
      agentId: createDraft.agentId.trim(),
      name: createDraft.name.trim(),
      primaryAbility: createDraft.primaryAbility.trim(),
    };
    if (!profile.agentId || !profile.name || !profile.primaryAbility) {
      setCreateError("Agent ID、Agent 名称和主能力均不能为空");
      return;
    }
    setCreateError(null);
    onCreateAgent(roleKey, profile);
  };

  return (
    <Card role="region" aria-label={`${meta.label}成员`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{meta.label}</CardTitle>
          <Badge variant={structureOk ? "success" : "destructive"}>
            {current}/{required}
            {missing ? " · 缺" : ""}
          </Badge>
        </div>
        <CardDescription>成员来源：智能生成占位或选择已有 Agent</CardDescription>
        <div className="space-y-1 border-t pt-2 text-xs leading-5 text-muted-foreground">
          <p>{meta.responsibility}</p>
          <p>{meta.boundary}</p>
          <p className="text-[11px]">职责依据：AI Scientist 文档 §4.3–§4.6。</p>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 模式切换 */}
        <div className="inline-flex rounded-md border bg-muted/40 p-0.5">
          {(
            [
              { mode: "generate", label: "智能生成" },
              { mode: "existing", label: "选择已有" },
            ] as const
          ).map((opt) => (
            <button
              key={opt.mode}
              type="button"
              onClick={() => onChangeRole({ mode: opt.mode })}
              className={cn(
                "rounded px-3 py-1 text-xs font-medium transition-colors",
                draft.mode === opt.mode
                  ? "bg-secondary text-secondary-foreground shadow"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {draft.mode === "generate" ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={draft.count <= meta.minCount}
                onClick={() =>
                  onChangeRole({
                    count: draft.count - 1,
                    generateProfiles: resizeProfiles(roleKey, draft.generateProfiles, draft.count - 1),
                  })
                }
                aria-label="减少数量"
              >
                <Minus className="size-4" />
              </Button>
              <span className="min-w-8 text-center text-sm font-medium">{draft.count}</span>
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={draft.count >= meta.maxCount}
                onClick={() =>
                  onChangeRole({
                    count: draft.count + 1,
                    generateProfiles: resizeProfiles(roleKey, draft.generateProfiles, draft.count + 1),
                  })
                }
                aria-label="增加数量"
              >
                <Plus className="size-4" />
              </Button>
              <span className="text-xs text-muted-foreground">
                智能生成占位成员（创建后为 pending_generation）
              </span>
            </div>
            {/* 待生成槽位：预览 + 编辑 */}
            <div className="space-y-2">
              {draft.generateProfiles.map((profile, i) => (
                <SlotCard
                  key={i}
                  index={i}
                  profile={profile}
                  roleKey={roleKey}
                  onProfileChange={(p) => {
                    const next = [...draft.generateProfiles];
                    next[i] = p;
                    onChangeRole({ generateProfiles: next });
                  }}
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {agentsLoading && <p className="text-xs text-muted-foreground">加载 Agent 列表中…</p>}
            {agentsError !== null && (
              <div className="flex items-center gap-2 text-xs text-destructive">
                <span>{agentsError}</span>
                <Button type="button" variant="outline" size="sm" onClick={onReloadAgents}>
                  重试
                </Button>
              </div>
            )}
            {!agentsLoading && agentsError === null && roleAgents.length === 0 && (
              <p className="text-xs text-muted-foreground">当前没有可选的{meta.label} Agent。</p>
            )}
            {roleAgents.map((agent) => {
              const selected = draft.agentIds.includes(agent.agent_id);
              const detailOpen = detailAgentId === agent.agent_id;
              return (
                <div key={agent.agent_id} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <label
                      htmlFor={`agent-${roleKey}-${agent.agent_id}`}
                      className={cn(
                        "flex flex-1 cursor-pointer items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors",
                        selected
                          ? "border-primary bg-primary/10"
                          : "border-input hover:bg-accent",
                      )}
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <input
                          id={`agent-${roleKey}-${agent.agent_id}`}
                          type="checkbox"
                          checked={selected}
                          onChange={(event) => {
                            const next = event.target.checked
                              ? [...new Set([...draft.agentIds, agent.agent_id])]
                              : draft.agentIds.filter((id) => id !== agent.agent_id);
                            onChangeRole({ agentIds: next });
                          }}
                          aria-label={`${agent.name}（${meta.label}）`}
                          className="size-4 shrink-0 accent-primary"
                        />
                        <span className="min-w-0">
                        <span className="font-medium">{agent.name}</span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {agent.primary_ability ?? agent.agent_id}
                        </span>
                        </span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <Badge variant={agent.enabled ? "success" : "destructive"}>
                          {agent.enabled ? "已启用" : "已停用"}
                        </Badge>
                        <Badge variant={testStatusVariant(agent)}>
                          {testStatusLabel(agent)}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {selected ? "已选择" : "未选择"}
                        </span>
                      </span>
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setDetailAgentId(detailOpen ? null : agent.agent_id)}
                    >
                      {detailOpen ? "收起" : "详情"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!agent.enabled || testingAgentId !== null}
                      onClick={() => onTestAgent(agent.agent_id)}
                    >
                      {testingAgentId === agent.agent_id ? "测试中…" : "测试 Agent"}
                    </Button>
                  </div>
                  {detailOpen && <AgentInfoCard agent={agent} />}
                  {agent.latest_test?.error && (
                    <p className="px-3 text-xs text-destructive">{agent.latest_test.error}</p>
                  )}
                </div>
              );
            })}
            <div className="space-y-3 rounded-md border border-dashed bg-muted/20 p-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setCreateFormOpen((open) => !open)}
              >
                <Plus className="size-3.5" />
                {createFormOpen ? "收起创建表单" : "创建 Agent Profile"}
              </Button>
              {createFormOpen && (
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="space-y-1">
                    <label htmlFor={`create-agent-id-${roleKey}`} className="text-xs font-medium">
                      Agent ID
                    </label>
                    <Input
                      id={`create-agent-id-${roleKey}`}
                      value={createDraft.agentId}
                      onChange={(event) => updateCreateDraft({ agentId: event.target.value })}
                      placeholder="稳定 ID"
                    />
                  </div>
                  <div className="space-y-1">
                    <label htmlFor={`create-agent-name-${roleKey}`} className="text-xs font-medium">
                      Agent 名称
                    </label>
                    <Input
                      id={`create-agent-name-${roleKey}`}
                      value={createDraft.name}
                      onChange={(event) => updateCreateDraft({ name: event.target.value })}
                      placeholder="展示名称"
                    />
                  </div>
                  <div className="space-y-1">
                    <label htmlFor={`create-agent-ability-${roleKey}`} className="text-xs font-medium">
                      主能力
                    </label>
                    <Input
                      id={`create-agent-ability-${roleKey}`}
                      value={createDraft.primaryAbility}
                      onChange={(event) => updateCreateDraft({ primaryAbility: event.target.value })}
                      placeholder="主要科研能力"
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-2 md:col-span-3">
                    <Button
                      type="button"
                      size="sm"
                      disabled={creatingAgentRole !== null}
                      onClick={submitCreateAgent}
                    >
                      {creatingAgentRole === roleKey ? "保存中…" : "保存 Agent Profile"}
                    </Button>
                    {createError !== null && (
                      <p className="text-xs text-destructive">{createError}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
            {roleKey === "master_student" && (
              <p className="text-xs text-muted-foreground">
                当前勾选 {draft.agentIds.length}/{required} 人；不足时可继续勾选或改用智能生成补齐。
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function StepMembers({
  draft,
  agents,
  agentsError,
  creatingAgentRole,
  testingAgentId,
  agentActionError,
  onReloadAgents,
  onCreateAgent,
  onTestAgent,
  onChange,
  onNext,
  onBack,
  onCancel,
}: Props) {
  const structure = validateStructure(draft.memberSelection);
  const agentsLoading = agents === null && agentsError === null;

  const updateRole = (roleKey: RoleKey, patch: Partial<RoleDraft>) => {
    onChange({
      memberSelection: {
        ...draft.memberSelection,
        [roleKey]: { ...draft.memberSelection[roleKey], ...patch },
      },
    });
  };

  const applyDefault = () => {
    onChange({
      memberSelection: {
        postdoc: { mode: "generate", agentIds: [], count: 1, generateProfiles: createDefaultProfiles("postdoc", 1) },
        phd_student: { mode: "generate", agentIds: [], count: 1, generateProfiles: createDefaultProfiles("phd_student", 1) },
        master_student: { mode: "generate", agentIds: [], count: 3, generateProfiles: createDefaultProfiles("master_student", 3) },
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>成员选择</CardTitle>
            <CardDescription>按科研角色配置成员，每个角色可智能生成或选择已有 Agent。</CardDescription>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={applyDefault}>
            <RotateCcw className="size-3.5" />
            一键默认配置
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {(Object.keys(ROLE_META) as RoleKey[]).map((roleKey) => (
          <RoleSection
            key={roleKey}
            roleKey={roleKey}
            draft={draft.memberSelection[roleKey]}
            roleAgents={
              agents?.filter((a) => a.role === ROLE_META[roleKey].roleValue) ?? []
            }
            agentsLoading={agentsLoading}
            agentsError={agentsError}
            creatingAgentRole={creatingAgentRole}
            testingAgentId={testingAgentId}
            onReloadAgents={onReloadAgents}
            onCreateAgent={onCreateAgent}
            onTestAgent={onTestAgent}
            onChangeRole={(patch) => updateRole(roleKey, patch)}
            structureOk={!structure.missing.includes(roleKey)}
          />
        ))}

        {agentActionError !== null && (
          <p className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            Agent 操作失败：{agentActionError}
          </p>
        )}

        {/* 结构校验条 */}
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs">
          {(Object.keys(ROLE_META) as RoleKey[]).map((roleKey) => {
            const ok = !structure.missing.includes(roleKey);
            return (
              <span key={roleKey} className={ok ? "text-ok" : "font-medium text-destructive"}>
                {ok ? "✓" : "✗"} {ROLE_META[roleKey].countLabel}
              </span>
            );
          })}
        </div>
      </CardContent>
      <CardFooter className="justify-between">
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onCancel}>
            取消
          </Button>
          <Button variant="outline" onClick={onBack}>
            上一步
          </Button>
        </div>
        <Button disabled={!structure.ok} onClick={onNext}>
          下一步
        </Button>
      </CardFooter>
    </Card>
  );
}
