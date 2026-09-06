import type { GenerateProfile } from "@/lib/api";

type PendingMember = {
  role: string;
  displayName: string;
  generateProfile: GenerateProfile | null;
};

const DEFAULT_ABILITY_BY_ROLE: Record<string, string> = {
  postdoc: "研究任务协调",
  phd_student: "研究问题整合",
  master_student: "独立科研分析",
};

function fallbackDisplayName(member: PendingMember): string {
  const cleaned = member.displayName.replace(/^待生成/, "").trim();
  return cleaned || `${member.role} Agent`;
}

/** Supply a safe editable default for legacy members that were created without a profile. */
export function defaultMemberConfiguration(member: PendingMember): GenerateProfile {
  return {
    ...(member.generateProfile ?? {}),
    display_name:
      member.generateProfile?.display_name?.trim() || fallbackDisplayName(member),
    primary_ability:
      member.generateProfile?.primary_ability?.trim()
      || DEFAULT_ABILITY_BY_ROLE[member.role]
      || "独立科研分析",
  };
}
