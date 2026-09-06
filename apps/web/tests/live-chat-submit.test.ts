import assert from "node:assert/strict";
import { test } from "node:test";

import { submitLiveChatDraft } from "../lib/live-chat-submit";

const mention = {
  type: "member" as const,
  id: "member-1",
  label: "证据博士",
  role: "博士",
};

test("an @ instruction persists the user bubble before a blocked clarification", async () => {
  const calls: string[] = [];
  const result = await submitLiveChatDraft({
    groupChatId: "gc-1",
    draft: { text: "分析资料中的强度证据", mention },
    pendingClarification: null,
    api: {
      saveMessage: async (request) => {
        calls.push(`message:${request.content}`);
        return { id: "msg-user-1" };
      },
      createClarification: async (request) => {
        calls.push(`clarification:${request.source_message_id}`);
        return { id: "clarification-1", status: "blocked" };
      },
      answerClarification: async () => {
        throw new Error("a blocked clarification must not be answered");
      },
    },
  });

  assert.deepEqual(calls, [
    "message:分析资料中的强度证据",
    "clarification:msg-user-1",
  ]);
  assert.equal(result.pendingClarification, null);
});

test("a normal message after a blocked clarification remains a normal user bubble", async () => {
  const calls: string[] = [];
  await submitLiveChatDraft({
    groupChatId: "gc-1",
    draft: { text: "补充实验条件", mention: null },
    pendingClarification: null,
    api: {
      saveMessage: async (request) => {
        calls.push(`message:${request.content}`);
        return { id: "msg-user-2" };
      },
      createClarification: async () => {
        throw new Error("normal messages must not create a clarification");
      },
      answerClarification: async () => {
        throw new Error("normal messages must not answer a clarification");
      },
    },
  });

  assert.deepEqual(calls, ["message:补充实验条件"]);
});

test("a clarification answer persists its user bubble and keeps the source message id", async () => {
  let sourceMessageId = "";
  const result = await submitLiveChatDraft({
    groupChatId: "gc-1",
    draft: { text: "关注抗压强度和孔径分布", mention: null },
    pendingClarification: { id: "clarification-1", status: "awaiting_answer" },
    api: {
      saveMessage: async () => ({ id: "msg-answer-1" }),
      createClarification: async () => {
        throw new Error("an answer must not start another clarification");
      },
      answerClarification: async (clarificationId, request) => {
        assert.equal(clarificationId, "clarification-1");
        sourceMessageId = request.source_message_id ?? "";
        return { id: clarificationId, status: "ready_to_assign" };
      },
    },
  });

  assert.equal(sourceMessageId, "msg-answer-1");
  assert.equal(result.pendingClarification, null);
  assert.equal(result.readyToStart, true);
});
