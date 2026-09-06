"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { roleLabel } from "@/components/run/labels";
import type { AgentProfile } from "@/lib/api";

type Props = {
  agent: AgentProfile;
};

const ROLE_RESPONSIBILITIES: Record<string, string> = {
  postdoc:
    "唯一接入受治理垂直领域知识库，在专业范围内参与讨论并独立科学审核；超出范围必须拒答。",
  phd_student:
    "承担课题唯一整合责任，比较竞争性解释、组织辩论与组会并更新研究状态；不替导师批准重大决策。",
  master_student:
    "作为长期科研身份的独立研究者开展机制探索、文献研究、实验设计、数据分析和科研写作；不批准实验或结论。",
};

function joinAbilities(agent: AgentProfile): string {
  const parts = [
    agent.primary_ability,
    ...agent.secondary_abilities,
    ...agent.general_research_abilities,
  ].filter((s): s is string => typeof s === "string" && s.length > 0);
  return parts.length > 0 ? parts.join("、") : "—";
}

export function AgentInfoCard({ agent }: Props) {
  const domain = agent.specialty_domain ?? "合成科研 demo";
  const skills = agent.general_research_abilities.filter((s) => s.length > 0);
  const tools =
    agent.allowed_tools.length > 0 ? agent.allowed_tools : ["文件 + 搜索（默认）"];
  const dataSpaces =
    agent.allowed_data_spaces.length > 0 ? agent.allowed_data_spaces : ["synthetic"];

  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">{agent.name}</CardTitle>
          <Badge variant="secondary">{roleLabel(agent.role)}</Badge>
        </div>
        <CardDescription>
          {roleLabel(agent.role)}，主能力 {agent.primary_ability ?? "未声明"}
        </CardDescription>
        <p className="text-xs leading-5 text-muted-foreground">
          {ROLE_RESPONSIBILITIES[agent.role] ?? "按当前 Agent 配置执行科研协作任务。"}
        </p>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>
          <span className="font-medium">领域/行业：</span>
          <span className="text-muted-foreground">{domain}</span>
        </p>
        <p>
          <span className="font-medium">特点：</span>
          <span className="text-muted-foreground">{joinAbilities(agent)}</span>
        </p>
        {skills.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium">Skills：</span>
            {skills.map((s) => (
              <Badge key={s} variant="outline">
                {s}
              </Badge>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-medium">Tools：</span>
          {tools.map((t) => (
            <Badge key={t} variant="outline">
              {t}
            </Badge>
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {dataSpaces.map((d) => (
            <Badge key={d} variant="secondary">
              data: {d}
            </Badge>
          ))}
        </div>
        {agent.forbidden_actions !== null && agent.forbidden_actions.length > 0 && (
          <p className="text-xs text-muted-foreground">权限边界：{agent.forbidden_actions}</p>
        )}
      </CardContent>
    </Card>
  );
}
