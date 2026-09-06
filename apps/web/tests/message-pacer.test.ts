import assert from "node:assert/strict";
import { test } from "node:test";

import { MessagePacer, type Clock } from "../lib/message-pacer";
import { toTimelineItem } from "../components/group-chat/chat-types";
import type { ChatMessageRecord } from "../lib/api";

class FakeClock implements Clock {
  private value: number;

  constructor(start: number) {
    this.value = start;
  }

  now(): number {
    return this.value;
  }

  advance(ms: number): void {
    this.value += ms;
  }
}

test("shows typing at 250 ms and first agent text at 900 ms", () => {
  const clock = new FakeClock(0);
  const pacer = new MessagePacer(clock);
  pacer.enqueue({
    id: "a-1",
    replyToId: "u-1",
    receivedAt: 40,
    sentAt: 0,
    content: "已收到，我先核对资料。",
  });
  clock.advance(249);
  assert.deepEqual(pacer.snapshot(), [{ id: "a-1", typing: false, visibleText: "" }]);
  clock.advance(1);
  assert.equal(pacer.snapshot()[0].typing, true);
  clock.advance(649);
  assert.equal(pacer.snapshot()[0].visibleText, "");
  clock.advance(1);
  assert.ok(pacer.snapshot()[0].visibleText.length > 0);
});

function message(
  partial: Partial<ChatMessageRecord> & {
    sender_type: ChatMessageRecord["sender_type"];
    content: string;
  },
): ChatMessageRecord {
  return {
    id: "m-1",
    group_chat_id: "g-1",
    sender_id: null,
    mention: null,
    task_id: null,
    attachment_ids: [],
    created_at: 0,
    data_space: "desensitized_real",
    ...partial,
  };
}

test("timeline maps user attachment right and postdoc update left", () => {
  const members = [
    { id: "postdoc", display_name: "博士后", role: "postdoc" },
    { id: "u-1", display_name: "我", role: "user" },
  ];
  const items = [
    toTimelineItem(
      message({ sender_type: "user", kind: "attachment", content: "实验记录.pdf" }),
      members,
    ),
    toTimelineItem(
      message({
        sender_type: "agent",
        sender_id: "postdoc",
        kind: "run_status",
        content: "资料已可检索",
      }),
      members,
    ),
  ];
  assert.equal(items[0].side, "right");
  assert.equal(items[1].side, "left");
  assert.equal(items[1].senderName, "博士后");
});

test("queues adjacent status messages and does not replay restored history", () => {
  const clock = new FakeClock(0);
  const pacer = new MessagePacer(clock);
  pacer.enqueue({
    id: "status-1",
    replyToId: "u-1",
    receivedAt: 0,
    sentAt: 0,
    kind: "run_status",
    content: "正在检索资料",
  });
  pacer.enqueue({
    id: "status-2",
    replyToId: "u-1",
    receivedAt: 0,
    sentAt: 0,
    kind: "run_status",
    content: "正在整理候选结论",
  });
  clock.advance(900);
  assert.ok(
    (pacer.snapshot().find((item) => item.id === "status-1")?.visibleText.length ?? 0) > 0,
  );
  assert.equal(pacer.snapshot().find((item) => item.id === "status-2")?.typing, false);
  pacer.restore(["status-1"]);
  clock.advance(699);
  assert.equal(pacer.snapshot().find((item) => item.id === "status-2")?.visibleText, "");
  clock.advance(1);
  assert.equal(pacer.snapshot().find((item) => item.id === "status-2")?.typing, true);
});
