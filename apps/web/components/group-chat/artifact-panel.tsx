"use client";

import { useState } from "react";

import type { RunArtifact } from "@/lib/api";
import { cn } from "@/lib/utils";
import { displayNameForSenderId, type TimelineMember } from "./chat-types";

type Props = {
  /** 群聊成员（每个成员一个文件夹）。 */
  members: Array<{
    id: string;
    displayName: string;
    agentProfileRef?: { object_type: string; object_id: string } | null;
  }>;
  /** 当前 Run 从服务端返回的持久化产物。 */
  artifacts: RunArtifact[];
};

export function ArtifactPanel({ members, artifacts }: Props) {
  const persistedArtifacts = artifacts.filter(
    (artifact) => artifact.artifact_type === "master_research_markdown",
  );
  const artifactByAgent = new Map<string, RunArtifact[]>();
  for (const artifact of persistedArtifacts) {
    const current = artifactByAgent.get(artifact.agent_id) ?? [];
    current.push(artifact);
    artifactByAgent.set(artifact.agent_id, current);
  }

  const timelineMembers: TimelineMember[] = members.map((member) => ({
    id: member.id,
    display_name: member.displayName,
    agent_id: member.agentProfileRef?.object_id?.replace(/^agent:/, "") ?? undefined,
  }));

  const folders = [
    ...members.map((member) => ({
      id: member.id,
      name: member.displayName,
      files: artifactByAgent.get(
        timelineMembers.find((candidate) => candidate.id === member.id)?.agent_id ?? member.id,
      ) ?? [],
    })),
    ...[...artifactByAgent.entries()]
      .filter(([agentId]) => displayNameForSenderId(agentId, timelineMembers) === null)
      .map(([agentId, files]) => ({ id: agentId, name: agentId, files })),
    { id: "例会记录", name: "例会记录", files: [] as RunArtifact[] },
  ];
  const [openFolders, setOpenFolders] = useState<string[]>(() =>
    folders.filter((folder) => folder.files.length > 0).map((folder) => folder.id),
  );

  const toggleFolder = (folderId: string) => {
    setOpenFolders((current) =>
      current.includes(folderId)
        ? current.filter((id) => id !== folderId)
        : [...current, folderId],
    );
  };

  return (
    <div className="rounded-md border bg-card p-3">
      <div className="mb-2 space-y-1">
        <p className="text-sm font-medium">产物面板</p>
        <p className="text-xs text-muted-foreground">当前 Run 的服务端产物</p>
        <p className="text-xs text-muted-foreground">
          每个硕士 Agent 独立生成一份 Markdown，作为博士组会前审查和 PI 决策的依据。
        </p>
      </div>

      <div className="space-y-1">
        {folders.map((folder) => {
          const open = openFolders.includes(folder.id);
          return (
            <div key={folder.id} className="rounded-md border bg-muted/20">
              <button
                type="button"
                onClick={() => toggleFolder(folder.id)}
                className={cn(
                  "flex w-full items-center justify-between px-2.5 py-1.5 text-left text-xs",
                  "hover:bg-secondary/40",
                )}
              >
                <span className="font-medium">
                  {folder.id === "例会记录" ? "🗂" : "📁"} {folder.name}
                </span>
                <span className="text-muted-foreground">{open ? "−" : "+"}</span>
              </button>
              {open && (
                <div className="space-y-1 px-2.5 pb-2 pt-0.5">
                  {folder.files.length > 0 ? (
                    folder.files.map((artifact) => (
                      <div
                        key={artifact.artifact_id}
                        className="truncate rounded bg-background px-2 py-1 font-mono text-[11px] text-muted-foreground"
                      >
                        <p>{artifact.filename}{artifact.version ? ` · v${artifact.version}` : ""}</p>
                        {artifact.source_refs && artifact.source_refs.length > 0 && (
                          <p className="mt-0.5 truncate font-sans text-[10px]">来源：{artifact.source_refs.join(", ")}</p>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="px-2 py-1 text-[11px] text-muted-foreground">
                      当前 Run 暂无持久化产物
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
