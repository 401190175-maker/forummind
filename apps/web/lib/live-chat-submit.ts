import type {
  ChatMessageRecord,
  CreateMessageRequest,
  TaskClarificationAnswerRequest,
  TaskClarificationRequest,
  TaskClarificationResponse,
  DatasetVersionRef,
} from "./api";
import type { PendingClarification } from "@/components/group-chat/live-chat-state";

export type LiveChatMention = {
  type: "all" | "role" | "member";
  id: string;
  label: string;
};

export type LiveChatDraft = {
  text: string;
  mention: LiveChatMention | null;
};

type ClarificationResult = Pick<TaskClarificationResponse, "id" | "status">;

export type LiveChatSubmitApi = {
  saveMessage: (request: CreateMessageRequest) => Promise<Pick<ChatMessageRecord, "id">>;
  createClarification: (request: TaskClarificationRequest) => Promise<ClarificationResult>;
  answerClarification: (
    clarificationId: string,
    request: TaskClarificationAnswerRequest,
  ) => Promise<ClarificationResult>;
};

export type LiveChatSubmitResult = {
  pendingClarification: PendingClarification | null;
  readyToStart: boolean;
};

function mentionDto(mention: LiveChatMention) {
  return {
    target_type: mention.type,
    target_id: mention.id,
    label: mention.label,
  } as const;
}

function resultFor(response: ClarificationResult): LiveChatSubmitResult {
  return {
    pendingClarification:
      response.status === "awaiting_answer"
        ? { id: response.id, status: "awaiting_answer" }
        : null,
    readyToStart: response.status === "ready_to_assign",
  };
}

/** Persist the user text first so every chat action has a durable right-side bubble. */
export async function submitLiveChatDraft({
  groupChatId,
  draft,
  pendingClarification,
  api,
  selectedDatasetRefs,
}: {
  groupChatId: string;
  draft: LiveChatDraft;
  pendingClarification: PendingClarification | null;
  api: LiveChatSubmitApi;
  selectedDatasetRefs?: DatasetVersionRef[];
}): Promise<LiveChatSubmitResult> {
  const mention = draft.mention ? mentionDto(draft.mention) : null;
  const userMessage = await api.saveMessage({ content: draft.text, mention });

  if (pendingClarification !== null) {
    const response = await api.answerClarification(pendingClarification.id, {
      answer: draft.text,
      source_message_id: userMessage.id,
    });
    return resultFor(response);
  }

  if (mention === null) {
    return { pendingClarification: null, readyToStart: false };
  }

  const response = await api.createClarification({
    initial_intent: draft.text,
    mention,
    source_message_id: userMessage.id,
    dataset_refs: selectedDatasetRefs ?? [],
  });
  return resultFor(response);
}
