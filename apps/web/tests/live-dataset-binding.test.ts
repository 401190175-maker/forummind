import assert from "node:assert/strict";
import { test } from "node:test";

import { submitLiveChatDraft } from "../lib/live-chat-submit";

const mention = { type: "member" as const, id: "member-1", label: "资料分析员" };
const refs = [{ dataset_id: "dataset-1", version: 2 }];

test("only the initial @ clarification receives the explicit dataset version refs", async () => {
  let createdBody: Record<string, unknown> | undefined;
  let answeredBody: Record<string, unknown> | undefined;
  await submitLiveChatDraft({
    groupChatId: "group-a",
    draft: { text: "分析强度", mention },
    pendingClarification: null,
    selectedDatasetRefs: refs,
    api: {
      saveMessage: async () => ({ id: "message-1" }),
      createClarification: async (body) => {
        createdBody = body as unknown as Record<string, unknown>;
        return { id: "clarification-1", status: "awaiting_answer" };
      },
      answerClarification: async () => {
        throw new Error("not used");
      },
    },
  });
  await submitLiveChatDraft({
    groupChatId: "group-a",
    draft: { text: "关注抗压强度", mention: null },
    pendingClarification: { id: "clarification-1", status: "awaiting_answer" },
    selectedDatasetRefs: [{ dataset_id: "dataset-1", version: 3 }],
    api: {
      saveMessage: async () => ({ id: "message-2" }),
      createClarification: async () => { throw new Error("not used"); },
      answerClarification: async (_id, body) => {
        answeredBody = body as unknown as Record<string, unknown>;
        return { id: "clarification-1", status: "ready_to_assign" };
      },
    },
  });

  assert.deepEqual(createdBody?.dataset_refs, refs);
  assert.equal("dataset_refs" in (answeredBody ?? {}), false);
});
