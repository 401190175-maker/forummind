import assert from "node:assert/strict";
import { test } from "node:test";

import {
  mentionTargetsForActiveMembers,
  pendingClarificationFromHistory,
} from "../components/group-chat/live-chat-state";

test("only configured members are available to @", () => {
  const targets = mentionTargetsForActiveMembers([
    { id: "postdoc-pending", role: "postdoc", displayName: "待配置博士后", status: "pending_generation" },
    { id: "phd-active", role: "phd_student", displayName: "证据博士", status: "active" },
    { id: "master-pending", role: "master_student", displayName: "待配置硕士", status: "pending_generation" },
  ]);

  assert.deepEqual(targets.map((target) => target.id), ["all", "role:phd_student", "phd-active"]);
});

test("a blocked clarification does not consume the next chat message", () => {
  const pending = pendingClarificationFromHistory([
    { id: "clarification-1", status: "awaiting_answer" },
    { id: "clarification-2", status: "blocked" },
  ]);

  assert.equal(pending, null);
});

test("the newest open clarification is restored after reopening a group", () => {
  const pending = pendingClarificationFromHistory([
    { id: "clarification-1", status: "ready_to_assign" },
    { id: "clarification-2", status: "awaiting_answer" },
  ]);

  assert.deepEqual(pending, { id: "clarification-2", status: "awaiting_answer" });
});
