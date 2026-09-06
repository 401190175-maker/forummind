"use client";

import { useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AgentInfoCard } from "@/components/agent-info-card";
import { AgentProfileEditor } from "@/components/agent-profile-editor";
import { roleLabel } from "@/components/run/labels";
import {
  createAgent,
  listAgents,
  updateAgent,
  type AgentProfile,
  type AgentRecord,
} from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";

type RoleFilter =
  | "all"
  | "postdoc"
  | "phd_student"
  | "master_student"
  | "group_meeting_secretary";

const ROLE_FILTERS: Array<{ value: RoleFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "postdoc", label: "博后" },
  { value: "phd_student", label: "博士" },
  { value: "master_student", label: "硕士" },
  { value: "group_meeting_secretary", label: "组会秘书" },
];

export default function PlazaPage() {
  const [agents, setAgents] = useState<AgentRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const [editorMode, setEditorMode] = useState<"create" | "edit" | null>(null);
  const [editorDraft, setEditorDraft] = useState<AgentProfile | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const emptyProfile = (): AgentProfile => ({
    agent_id: "",
    name: "",
    role: "master_student",
    description: null,
    primary_ability: "",
    secondary_abilities: [],
    general_research_abilities: [],
    allowed_data_spaces: ["synthetic"],
    allowed_tools: [],
    forbidden_actions: null,
    specialty_domain: null,
    knowledge_base_coverage: null,
  });

  const load = async () => {
    setError(null);
    setAgents(null);
    try {
      const res = await listAgents();
      setAgents(res.agents);
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "无法加载 Agent 列表",
      );
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openCreate = () => {
    setSaveError(null);
    setEditorDraft(emptyProfile());
    setEditorMode("create");
  };

  const openEdit = (agent: AgentRecord) => {
    setSaveError(null);
    setEditorDraft({
      agent_id: agent.agent_id,
      name: agent.name,
      role: agent.role,
      description: agent.description,
      primary_ability: agent.primary_ability,
      secondary_abilities: [...agent.secondary_abilities],
      general_research_abilities: [...agent.general_research_abilities],
      allowed_data_spaces: [...agent.allowed_data_spaces],
      allowed_tools: [...agent.allowed_tools],
      forbidden_actions: agent.forbidden_actions,
      specialty_domain: agent.specialty_domain,
      knowledge_base_coverage: agent.knowledge_base_coverage,
    });
    setEditorMode("edit");
  };

  const saveProfile = async () => {
    if (editorDraft === null) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = editorMode === "create"
        ? await createAgent(editorDraft)
        : await updateAgent(editorDraft.agent_id, editorDraft);
      setAgents((current) => {
        if (current === null) return [saved];
        return editorMode === "create"
          ? [...current, saved]
          : current.map((agent) => agent.agent_id === saved.agent_id ? saved : agent);
      });
      setDetailId(saved.agent_id);
      setEditorMode(null);
      setEditorDraft(null);
    } catch (err) {
      setSaveError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "保存 Agent 配置失败，请重试",
      );
    } finally {
      setSaving(false);
    }
  };

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleAgents =
    agents?.filter((agent) => {
      const matchesRole = roleFilter === "all" || agent.role === roleFilter;
      const searchableText = [
        agent.name,
        agent.role,
        roleLabel(agent.role),
        agent.primary_ability,
        ...agent.secondary_abilities,
        ...agent.general_research_abilities,
        agent.specialty_domain,
      ]
        .filter((value): value is string => typeof value === "string")
        .join(" ")
        .toLocaleLowerCase();
      return matchesRole && (normalizedQuery === "" || searchableText.includes(normalizedQuery));
    }) ?? null;

  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-2xl font-semibold tracking-tight">智能体广场</h1>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">浏览、配置和选择科研 Agent</p>
        <Button type="button" variant="outline" size="sm" onClick={openCreate}>
          <Plus aria-hidden="true" />
          创建 Agent
        </Button>
      </div>

      {editorMode !== null && editorDraft !== null && (
        <div className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle>{editorMode === "create" ? "创建 Agent" : "编辑 Agent"}</CardTitle>
              <CardDescription>
                保存后配置会进入服务端 Agent Profile，并用于后续课题组运行时指令。
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AgentProfileEditor
                profile={editorDraft}
                editing={editorMode === "edit"}
                onChange={setEditorDraft}
              />
              {saveError !== null && <p className="mt-3 text-sm text-destructive">{saveError}</p>}
            </CardContent>
            <div className="flex justify-end gap-2 px-6 pb-6">
              <Button type="button" variant="outline" onClick={() => setEditorMode(null)} disabled={saving}>
                取消
              </Button>
              <Button type="button" onClick={() => void saveProfile()} disabled={saving}>
                {saving ? "保存中…" : editorMode === "create" ? "保存 Agent" : "保存修改"}
              </Button>
            </div>
          </Card>
        </div>
      )}

      <div className="relative mt-6">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="搜索 Agent、能力或领域"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="搜索 Agent、能力或领域"
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-2" aria-label="按角色筛选">
        {ROLE_FILTERS.map((filter) => (
          <Button
            key={filter.value}
            type="button"
            size="sm"
            variant={roleFilter === filter.value ? "secondary" : "outline"}
            aria-pressed={roleFilter === filter.value}
            onClick={() => setRoleFilter(filter.value)}
          >
            {filter.label}
          </Button>
        ))}
      </div>

      <div className="mt-6">
        {agents === null && error === null && (
          <p className="text-sm text-muted-foreground">加载 Agent 列表中…</p>
        )}
        {error !== null && (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <span>{error}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
              重试
            </Button>
          </div>
        )}
        {agents !== null && visibleAgents !== null && visibleAgents.length === 0 && (
          <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            当前筛选没有匹配的 Agent。
            <Button
              type="button"
              variant="link"
              size="sm"
              className="ml-1"
              onClick={() => {
                setQuery("");
                setRoleFilter("all");
              }}
            >
              清除筛选
            </Button>
          </div>
        )}
        {visibleAgents !== null && visibleAgents.length > 0 && (
          <div className="grid gap-4 md:grid-cols-3">
            {visibleAgents.map((agent) => {
              const agentKey = agent.agent_id || `${agent.role}:${agent.name}`;
              const open = detailId === agentKey;
              return (
                <Card key={agentKey} aria-label={`Agent ${agent.agent_id}`}>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-base">{agent.name}</CardTitle>
                      <Badge variant="secondary">{roleLabel(agent.role)}</Badge>
                    </div>
                    <CardDescription>{agent.primary_ability ?? agent.agent_id}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">{agent.agent_id}</Badge>
                      <Badge variant="secondary">demo 数据</Badge>
                      <Badge variant={agent.enabled ? "success" : "destructive"}>
                        {agent.enabled ? "已启用" : "已停用"}
                      </Badge>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={() => setDetailId(open ? null : agentKey)}
                      >
                        {open ? "收起信息" : "查看信息"}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => openEdit(agent)}
                      >
                        编辑 Agent
                      </Button>
                    </div>
                  </CardContent>
                  {open && (
                    <div className="px-6 pb-6">
                      <AgentInfoCard agent={agent} />
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
