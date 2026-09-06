"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  createAgent,
  createGroupChat,
  listAgents,
  testAgent,
  type AgentRecord,
} from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import { recordFromResponse, useGroupChatStore } from "@/lib/stores/group-chat-store";
import { createDefaultDraft } from "./validation";
import { buildLiveGroupChatRequest } from "./request";
import type { RoleDraft, RoleKey, WizardDraft } from "./types";
import { StepBasics } from "./step-basics";
import { StepMembers, type CreateAgentDraft } from "./step-members";
import { StepConfirm } from "./step-confirm";
import { LIVE_RESEARCH_TOOLS } from "./generate-profiles";

type Props = {
  onClose: () => void;
};

export function GroupChatWizard({ onClose }: Props) {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [draft, setDraft] = useState<WizardDraft>(createDefaultDraft);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentRecord[] | null>(null);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [creatingAgentRole, setCreatingAgentRole] = useState<RoleKey | null>(null);
  const [testingAgentId, setTestingAgentId] = useState<string | null>(null);
  const [agentActionError, setAgentActionError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    setAgentsError(null);
    setAgents(null);
    try {
      const res = await listAgents();
      setAgents(res.agents);
    } catch (err) {
      setAgentsError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "无法加载 Agent 列表，请使用智能生成",
      );
    }
  }, []);

  const handleCreateAgent = async (role: RoleKey, profile: CreateAgentDraft) => {
    setCreatingAgentRole(role);
    setAgentActionError(null);
    try {
      const agent = await createAgent({
        agent_id: profile.agentId.trim(),
        name: profile.name.trim(),
        role,
        description: null,
        primary_ability: profile.primaryAbility.trim(),
        secondary_abilities: [],
        general_research_abilities: [],
        allowed_data_spaces: ["desensitized_real"],
        allowed_tools: [...LIVE_RESEARCH_TOOLS],
        forbidden_actions: null,
        specialty_domain: null,
        knowledge_base_coverage: null,
      });
      setAgents((current) => [...(current ?? []), agent]);
      setDraft((current) => ({
        ...current,
        memberSelection: {
          ...current.memberSelection,
          [role]: {
            ...current.memberSelection[role],
            mode: "existing",
            agentIds: [
              ...new Set([...current.memberSelection[role].agentIds, agent.agent_id]),
            ],
          },
        },
      }));
    } catch (err) {
      setAgentActionError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "创建 Agent Profile 失败，请重试",
      );
    } finally {
      setCreatingAgentRole(null);
    }
  };

  const handleTestAgent = async (agentId: string) => {
    setTestingAgentId(agentId);
    setAgentActionError(null);
    try {
      const result = await testAgent(
        agentId,
        "请说明你的科研职责、数据边界和当前可执行能力",
      );
      setAgents((current) =>
        current?.map((agent) =>
          agent.agent_id === agentId ? { ...agent, latest_test: result } : agent,
        ) ?? current,
      );
    } catch (err) {
      setAgentActionError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "Agent 测试失败，请重试",
      );
    } finally {
      setTestingAgentId(null);
    }
  };

  // Step2 首次进入时懒加载 Agent 列表。
  useEffect(() => {
    if (step === 2 && agents === null && agentsError === null) {
      void loadAgents();
    }
  }, [step, agents, agentsError, loadAgents]);

  const handleCancel = () => {
    setDraft(createDefaultDraft());
    setStep(1);
    setError(null);
    onClose();
  };

  const handleCreate = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const response = await createGroupChat(buildLiveGroupChatRequest(draft));
      useGroupChatStore.getState().set(recordFromResponse(response));
      router.push(`/groups/${response.group_chat.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof ApiConfigError
          ? err.message
          : "创建失败，请重试",
      );
      setSubmitting(false);
    }
  };

  if (step === 1) {
    return (
      <StepBasics
        draft={draft}
        onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
        onNext={() => setStep(2)}
        onCancel={handleCancel}
      />
    );
  }
  if (step === 2) {
    return (
      <StepMembers
        draft={draft}
        agents={agents}
        agentsError={agentsError}
        creatingAgentRole={creatingAgentRole}
        testingAgentId={testingAgentId}
        agentActionError={agentActionError}
        onReloadAgents={() => void loadAgents()}
        onCreateAgent={(role, profile) => void handleCreateAgent(role, profile)}
        onTestAgent={(agentId) => void handleTestAgent(agentId)}
        onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
        onNext={() => setStep(3)}
        onBack={() => setStep(1)}
        onCancel={handleCancel}
      />
    );
  }
  return (
    <StepConfirm
      draft={draft}
      agents={agents}
      submitting={submitting}
      error={error}
      onCreate={() => void handleCreate()}
      onBack={() => setStep(2)}
      onCancel={handleCancel}
    />
  );
}
