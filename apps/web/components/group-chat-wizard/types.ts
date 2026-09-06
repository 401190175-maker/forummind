/** 向导状态类型（design.md §4.1）。 */
import type { GenerateProfile } from "@/lib/api";

export type MemberMode = "existing" | "generate";

export type RoleDraft = {
  /** 成员来源模式。 */
  mode: MemberMode;
  /** existing：已勾选 Agent id（去重，按勾选顺序）。 */
  agentIds: string[];
  /** generate：生成数量（1–5）。 */
  count: number;
  /** generate：待生成槽位配置（长度=count，每槽位一个）。 */
  generateProfiles: GenerateProfile[];
};

export type RoleKey = "postdoc" | "phd_student" | "master_student";

export type WizardDraft = {
  topicName: string;
  topicSummary: string;
  memberSelection: Record<RoleKey, RoleDraft>;
};
