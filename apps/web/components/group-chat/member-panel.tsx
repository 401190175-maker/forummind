"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GenerateProfileEditor } from "@/components/group-chat-wizard/generate-profiles";
import type { GenerateProfile } from "@/lib/api";

import { defaultMemberConfiguration } from "./member-configuration";

type GroupMember = {
  id: string;
  role: string;
  displayName: string;
  status: string;
  generateProfile: GenerateProfile | null;
};

type Props = {
  members: GroupMember[];
  onConfigure: (memberId: string, configuration: GenerateProfile) => Promise<void>;
};

const ROLE_LABELS: Record<string, string> = {
  postdoc: "博士后",
  phd_student: "博士",
  master_student: "硕士",
  group_meeting_secretary: "组会秘书",
};

function statusLabel(status: string): { label: string; variant: "success" | "warning" | "outline" } {
  if (status === "active") return { label: "已配置", variant: "success" };
  if (status === "pending_generation") return { label: "待配置", variant: "warning" };
  return { label: "未就绪", variant: "outline" };
}

/** Configure generated members without taking the chat column out of its stable layout. */
export function MemberPanel({ members, onConfigure }: Props) {
  const [editingMemberId, setEditingMemberId] = useState<string | null>(null);
  const [configuration, setConfiguration] = useState<GenerateProfile | null>(null);
  const [savingMemberId, setSavingMemberId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const beginConfiguration = (member: GroupMember) => {
    setEditingMemberId(member.id);
    setConfiguration(defaultMemberConfiguration(member));
    setError(null);
  };

  const cancelConfiguration = () => {
    setEditingMemberId(null);
    setConfiguration(null);
    setError(null);
  };

  const confirmConfiguration = async (memberId: string) => {
    if (configuration === null) return;
    setSavingMemberId(memberId);
    setError(null);
    try {
      await onConfigure(memberId, configuration);
      cancelConfiguration();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "成员配置失败，请稍后重试");
    } finally {
      setSavingMemberId(null);
    }
  };

  return (
    <div className="divide-y border-y">
      {members.map((member) => {
        const status = statusLabel(member.status);
        const editing = editingMemberId === member.id;
        const saving = savingMemberId === member.id;
        return (
          <section key={member.id} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{member.displayName}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {ROLE_LABELS[member.role] ?? member.role}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant={status.variant}>{status.label}</Badge>
                {member.status === "pending_generation" && !editing && (
                  <Button type="button" size="sm" variant="outline" onClick={() => beginConfiguration(member)}>
                    配置
                  </Button>
                )}
              </div>
            </div>

            {editing && configuration !== null && (
              <div className="mt-3 space-y-3">
                <GenerateProfileEditor profile={configuration} onChange={setConfiguration} />
                {error !== null && <p className="text-xs text-destructive">{error}</p>}
                <div className="flex justify-end gap-2">
                  <Button type="button" size="sm" variant="ghost" disabled={saving} onClick={cancelConfiguration}>
                    取消
                  </Button>
                  <Button type="button" size="sm" disabled={saving} onClick={() => void confirmConfiguration(member.id)}>
                    {saving ? "配置中…" : "确认配置"}
                  </Button>
                </div>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
