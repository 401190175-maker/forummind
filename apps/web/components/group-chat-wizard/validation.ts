/** 向导校验纯函数（design.md §4.3），零 React 依赖，可独立验证。 */
import type { RoleDraft, RoleKey } from "./types";
import { createDefaultProfiles } from "./generate-profiles";

/** 文本字段：trim 后非空。 */
export function isNonEmpty(text: string): boolean {
  return text.trim().length > 0;
}

/** 角色成员数：existing 按 agentIds.length，generate 按 count。 */
export function roleCount(draft: RoleDraft): number {
  if (draft.mode === "existing") {
    return draft.agentIds.length;
  }
  return draft.count;
}

/** 默认最低科研组成员结构（与后端一致）：postdoc>=1、phd_student>=1、master_student>=3。 */
export const MIN_ROLE_COUNTS: Record<RoleKey, number> = {
  postdoc: 1,
  phd_student: 1,
  master_student: 3,
};

export type StructureResult = {
  ok: boolean;
  /** 缺失角色列表（数量不足的角色）。 */
  missing: RoleKey[];
};

/** 结构校验：返回是否满足最低成员结构及缺失角色列表。 */
export function validateStructure(ms: Record<RoleKey, RoleDraft>): StructureResult {
  const missing = (Object.keys(MIN_ROLE_COUNTS) as RoleKey[]).filter(
    (key) => roleCount(ms[key]) < MIN_ROLE_COUNTS[key],
  );
  return { ok: missing.length === 0, missing };
}

/** 一键默认配置草稿（design.md §4.2）：全 generate，1 博后 / 1 博士 / 3 硕士。 */
export function createDefaultDraft(): import("./types").WizardDraft {
  return {
    topicName: "",
    topicSummary: "",
    memberSelection: {
      postdoc: { mode: "generate", agentIds: [], count: 1, generateProfiles: createDefaultProfiles("postdoc", 1) },
      phd_student: { mode: "generate", agentIds: [], count: 1, generateProfiles: createDefaultProfiles("phd_student", 1) },
      master_student: { mode: "generate", agentIds: [], count: 3, generateProfiles: createDefaultProfiles("master_student", 3) },
    },
  };
}
