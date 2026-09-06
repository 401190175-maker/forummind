import type { TaskClarificationResponse } from "@/lib/api";

import type { MentionTarget } from "./types";

const ROLE_LABELS: Record<string, string> = {
  postdoc: "博士后",
  phd_student: "博士",
  master_student: "硕士",
  group_meeting_secretary: "组会秘书",
};

type ChatMember = {
  id: string;
  role: string;
  displayName: string;
  status: string;
};

export type PendingClarification = {
  id: string;
  status: "awaiting_answer";
};

/** Only enabled group members can receive a task clarification. */
export function mentionTargetsForActiveMembers(members: ChatMember[]): MentionTarget[] {
  const activeMembers = members.filter((member) => member.status === "active");
  const targets: MentionTarget[] = [];
  const hasActivePhd = activeMembers.some((member) => member.role === "phd_student");
  if (hasActivePhd) {
    targets.push({ type: "all", id: "all", label: "全体成员" });
  }

  const seenRoles = new Set<string>();
  for (const member of activeMembers) {
    if (!seenRoles.has(member.role)) {
      seenRoles.add(member.role);
      targets.push({
        type: "role",
        id: `role:${member.role}`,
        label: ROLE_LABELS[member.role] ?? member.role,
        role: ROLE_LABELS[member.role] ?? member.role,
      });
    }
    targets.push({
      type: "member",
      id: member.id,
      label: member.displayName,
      role: ROLE_LABELS[member.role] ?? member.role,
    });
  }
  return targets;
}

/** The latest closed or blocked clarification must not capture a new chat message. */
export function pendingClarificationFromHistory(
  clarifications: Array<Pick<TaskClarificationResponse, "id" | "status">>,
): PendingClarification | null {
  const latest = clarifications.at(-1);
  return latest?.status === "awaiting_answer"
    ? { id: latest.id, status: "awaiting_answer" }
    : null;
}
