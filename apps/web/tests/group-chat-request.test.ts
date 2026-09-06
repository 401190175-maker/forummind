import assert from "node:assert/strict";
import { test } from "node:test";

import { createDefaultDraft } from "../components/group-chat-wizard/validation";
import { buildLiveGroupChatRequest } from "../components/group-chat-wizard/request";

test("new browser groups use the live desensitized workspace", () => {
  const draft = createDefaultDraft();
  draft.topicName = "泡沫混凝土强度研究";
  draft.topicSummary = "核对孔结构与抗压强度的关系。";

  const request = buildLiveGroupChatRequest(draft);

  assert.equal(request.data_space, "desensitized_real");
  assert.equal(request.create_placeholder_tasks, false);
  assert.equal(request.member_selection.postdoc.selection_mode, "generate");
  assert.equal(request.member_selection.master_student.selection_mode, "generate");
  assert.deepEqual(
    request.member_selection.master_student.generate_profiles?.[0]?.allowed_tools,
    ["knowledge.search", "experiment.analyze", "literature.search"],
  );
});
