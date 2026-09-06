import assert from "node:assert/strict";
import { test } from "node:test";

import { toTimelineItem } from "../components/group-chat/chat-types";

test("timeline resolves every agent message through the member profile reference", () => {
  const members = [
    {
      id: "gc-1:master_student:agent-existing",
      display_name: "已有硕士 A",
      agent_id: "agent-existing",
    },
    {
      id: "gc-1:master_student:gen-1",
      display_name: "硕士 A Agent",
      agent_id: "agent-generated-b49906742970bd35",
    },
  ] as never;

  const existing = toTimelineItem(
    {
      id: "message-existing",
      group_chat_id: "gc-1",
      sender_type: "agent",
      sender_id: "agent-existing",
      content: "已有 Agent 消息",
      mention: null,
      task_id: null,
      attachment_ids: [],
      kind: "text",
      payload: {},
      reply_to_message_id: null,
      created_at: 1,
      data_space: "desensitized_real",
    },
    members,
  );
  const generated = toTimelineItem(
    {
      id: "message-generated",
      group_chat_id: "gc-1",
      sender_type: "agent",
      sender_id: "agent-generated-b49906742970bd35",
      content: "生成 Agent 消息",
      mention: null,
      task_id: null,
      attachment_ids: [],
      kind: "text",
      payload: {},
      reply_to_message_id: null,
      created_at: 2,
      data_space: "desensitized_real",
    },
    members,
  );

  assert.equal(existing.senderName, "已有硕士 A");
  assert.equal(generated.senderName, "硕士 A Agent");
});

test("timeline resolves agent-prefixed sender ids to the selected member name", () => {
  const members = [
    {
      id: "gc-1:master_student:gen-1",
      display_name: "硕士 A Agent",
      agent_id: "agent-generated-b49906742970bd35",
    },
  ] as never;

  const item = toTimelineItem(
    {
      id: "message-prefixed",
      group_chat_id: "gc-1",
      sender_type: "agent",
      sender_id: "agent:agent-generated-b49906742970bd35",
      content: "带前缀的 Agent 消息",
      mention: null,
      task_id: null,
      attachment_ids: [],
      kind: "text",
      payload: {},
      reply_to_message_id: null,
      created_at: 3,
      data_space: "desensitized_real",
    },
    members,
  );

  assert.equal(item.senderName, "硕士 A Agent");
});
