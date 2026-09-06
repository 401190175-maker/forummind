"use client";

import { useId } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { GenerateProfile } from "@/lib/api";
import type { RoleKey } from "./types";

export const LIVE_RESEARCH_TOOLS = [
  "knowledge.search",
  "experiment.analyze",
  "literature.search",
] as const;

/** 硕士 A/B/C 默认模板（对齐 demo 名录能力）。 */
export const MASTER_TEMPLATES = [
  {
    primary_ability: "文献与机制分析",
    description: "主能力：文献与机制分析；副能力：实验设计",
    skills: ["文献检索", "机制假设", "科研写作"],
  },
  {
    primary_ability: "实验与测试方法",
    description: "主能力：实验与测试方法；副能力：数据分析",
    skills: ["实验设计", "变量控制", "测试方法"],
  },
  {
    primary_ability: "数据与证据分析",
    description: "主能力：数据与证据分析；副能力：文献与机制分析",
    skills: ["数据核查", "统计分析", "证据评估"],
  },
] as const;

/** 角色默认模板工厂（design.md §4.1）：i 为槽位序号（0 起）。 */
export function createDefaultProfile(roleKey: RoleKey, i: number): GenerateProfile {
  if (roleKey === "postdoc") {
    return {
      display_name: "博士后 Agent",
      primary_ability: "实验约束核查与可检验预测",
      description: "唯一接入受治理垂直领域知识库；在声明的专业范围内参与讨论、独立审核并说明来源、边界、反例与限制",
      general_research_abilities: ["文献检索", "实验设计", "数据分析"],
      allowed_tools: [...LIVE_RESEARCH_TOOLS],
    };
  }
  if (roleKey === "phd_student") {
    return {
      display_name: "博士 Agent",
      primary_ability: "机理分析与候选解释构造",
      description: "承担课题唯一整合责任：明确研究问题、比较竞争性解释、组织辩论与组会，并更新研究状态",
      general_research_abilities: ["文献检索", "实验设计", "数据分析"],
      allowed_tools: [...LIVE_RESEARCH_TOOLS],
    };
  }
  const t = MASTER_TEMPLATES[i % MASTER_TEMPLATES.length];
  return {
    display_name: `硕士 ${"ABC"[i % MASTER_TEMPLATES.length]} Agent`,
    primary_ability: t.primary_ability,
    description: `${t.description}；作为具有长期科研身份的独立研究者开展机制探索、文献研究、实验设计、数据分析和科研写作`,
    general_research_abilities: [...t.skills],
    allowed_tools: [...LIVE_RESEARCH_TOOLS],
  };
}

/** 槽位工厂：生成 count 个默认 profile。 */
export function createDefaultProfiles(roleKey: RoleKey, count: number): GenerateProfile[] {
  return Array.from({ length: count }, (_, i) => createDefaultProfile(roleKey, i));
}

/** count 变更时重排槽位：保留已编辑前缀，新增用默认模板，删除尾部。 */
export function resizeProfiles(
  roleKey: RoleKey,
  current: GenerateProfile[],
  nextCount: number,
): GenerateProfile[] {
  const next = current.slice(0, nextCount);
  while (next.length < nextCount) {
    next.push(createDefaultProfile(roleKey, next.length));
  }
  return next;
}

/** 逗号/顿号分隔文本 → 列表。 */
function splitList(text: string): string[] {
  return text
    .split(/[,，、]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

type EditorProps = {
  profile: GenerateProfile;
  onChange: (p: GenerateProfile) => void;
};

/** 待生成槽位编辑表单（design.md §4.3）。 */
export function GenerateProfileEditor({ profile, onChange }: EditorProps) {
  const id = useId();
  const patch = (p: Partial<GenerateProfile>) => onChange({ ...profile, ...p });
  return (
    <div className="space-y-3 rounded-md border bg-muted/30 p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor={`${id}-name`} className="text-xs font-medium">名称</label>
          <Input
            id={`${id}-name`}
            value={profile.display_name ?? ""}
            placeholder="智能体名称"
            onChange={(e) => patch({ display_name: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor={`${id}-primary`} className="text-xs font-medium">主能力</label>
          <Input
            id={`${id}-primary`}
            value={profile.primary_ability ?? ""}
            placeholder="主能力"
            onChange={(e) => patch({ primary_ability: e.target.value })}
          />
        </div>
      </div>
      <div className="space-y-1">
        <label htmlFor={`${id}-description`} className="text-xs font-medium">背景/描述</label>
        <Textarea
          id={`${id}-description`}
          rows={2}
          value={profile.description ?? ""}
          placeholder="背景描述（可选）"
          onChange={(e) => patch({ description: e.target.value })}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor={`${id}-secondary`} className="text-xs font-medium">副能力（逗号分隔）</label>
        <Input
          id={`${id}-secondary`}
          value={(profile.secondary_abilities ?? []).join("、")}
          placeholder="如：实验设计、数据分析"
          onChange={(e) => patch({ secondary_abilities: splitList(e.target.value) })}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor={`${id}-skills`} className="text-xs font-medium">Skills（逗号分隔）</label>
        <Input
          id={`${id}-skills`}
          value={(profile.general_research_abilities ?? []).join("、")}
          placeholder="如：文献检索、实验设计"
          onChange={(e) => patch({ general_research_abilities: splitList(e.target.value) })}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor={`${id}-tools`} className="text-xs font-medium">Tools（逗号分隔，空 = 文件 + 搜索）</label>
        <Input
          id={`${id}-tools`}
          value={(profile.allowed_tools ?? []).join("、")}
          placeholder="如：文件解析、网络搜索"
          onChange={(e) => patch({ allowed_tools: splitList(e.target.value) })}
        />
      </div>
    </div>
  );
}
