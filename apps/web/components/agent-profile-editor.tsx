"use client";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { AgentProfile } from "@/lib/api";

type Props = {
  profile: AgentProfile;
  editing: boolean;
  onChange: (profile: AgentProfile) => void;
};

const ROLE_OPTIONS = [
  ["postdoc", "博士后"],
  ["phd_student", "博士"],
  ["master_student", "硕士"],
  ["group_meeting_secretary", "组会秘书"],
] as const;

function splitList(value: string): string[] {
  return value
    .split(/[,，、]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function AgentProfileEditor({ profile, editing, onChange }: Props) {
  const patch = (next: Partial<AgentProfile>) => onChange({ ...profile, ...next });
  return (
    <div className="space-y-3 rounded-md border bg-muted/20 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="agent-id" className="text-xs font-medium">Agent ID</label>
          <Input
            id="agent-id"
            value={profile.agent_id}
            disabled={editing}
            onChange={(event) => patch({ agent_id: event.target.value })}
            placeholder="稳定 ID"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="agent-name" className="text-xs font-medium">Agent 名称</label>
          <Input
            id="agent-name"
            value={profile.name}
            onChange={(event) => patch({ name: event.target.value })}
            placeholder="展示名称"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="agent-role" className="text-xs font-medium">科研角色</label>
          <select
            id="agent-role"
            value={profile.role}
            onChange={(event) => patch({ role: event.target.value })}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
          >
            {ROLE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="agent-primary-ability" className="text-xs font-medium">主能力</label>
          <Input
            id="agent-primary-ability"
            value={profile.primary_ability ?? ""}
            onChange={(event) => patch({ primary_ability: event.target.value })}
            placeholder="主要科研能力"
          />
        </div>
      </div>
      <div className="space-y-1">
        <label htmlFor="agent-description" className="text-xs font-medium">背景描述</label>
        <Textarea
          id="agent-description"
          rows={2}
          value={profile.description ?? ""}
          onChange={(event) => patch({ description: event.target.value })}
          placeholder="职责、经验和协作方式"
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="agent-specialty" className="text-xs font-medium">专业范围</label>
          <Input
            id="agent-specialty"
            value={profile.specialty_domain ?? ""}
            onChange={(event) => patch({ specialty_domain: event.target.value })}
            placeholder="专业领域"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="agent-knowledge" className="text-xs font-medium">知识库覆盖</label>
          <Input
            id="agent-knowledge"
            value={profile.knowledge_base_coverage ?? ""}
            onChange={(event) => patch({ knowledge_base_coverage: event.target.value })}
            placeholder="可引用的知识边界"
          />
        </div>
      </div>
      <div className="space-y-1">
        <label htmlFor="agent-secondary" className="text-xs font-medium">副能力（逗号分隔）</label>
        <Input
          id="agent-secondary"
          value={profile.secondary_abilities.join("、")}
          onChange={(event) => patch({ secondary_abilities: splitList(event.target.value) })}
          placeholder="实验设计、数据分析"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="agent-skills" className="text-xs font-medium">通用科研能力（逗号分隔）</label>
        <Input
          id="agent-skills"
          value={profile.general_research_abilities.join("、")}
          onChange={(event) => patch({ general_research_abilities: splitList(event.target.value) })}
          placeholder="文献检索、科研写作"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="agent-tools" className="text-xs font-medium">允许工具（逗号分隔）</label>
        <Input
          id="agent-tools"
          value={profile.allowed_tools.join("、")}
          onChange={(event) => patch({ allowed_tools: splitList(event.target.value) })}
          placeholder="memory.query、literature.search"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="agent-forbidden" className="text-xs font-medium">禁止动作</label>
        <Textarea
          id="agent-forbidden"
          rows={2}
          value={profile.forbidden_actions ?? ""}
          onChange={(event) => patch({ forbidden_actions: event.target.value })}
          placeholder="不得批准正式结论；不得越过数据边界"
        />
      </div>
    </div>
  );
}

