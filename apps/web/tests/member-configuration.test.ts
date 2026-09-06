import assert from "node:assert/strict";
import { test } from "node:test";

import { defaultMemberConfiguration } from "../components/group-chat/member-configuration";

test("a pending member receives a valid editable configuration by default", () => {
  const configuration = defaultMemberConfiguration({
    role: "master_student",
    displayName: "待生成硕士 Agent 1",
    generateProfile: null,
  });

  assert.equal(configuration.display_name, "硕士 Agent 1");
  assert.equal(configuration.primary_ability, "独立科研分析");
});

test("a pending member keeps fields already chosen in the creation wizard", () => {
  const configuration = defaultMemberConfiguration({
    role: "postdoc",
    displayName: "待生成博士后 Agent 1",
    generateProfile: {
      display_name: "资料协调博士后",
      primary_ability: "研究约束梳理",
      description: "管理资料和任务边界",
    },
  });

  assert.equal(configuration.display_name, "资料协调博士后");
  assert.equal(configuration.primary_ability, "研究约束梳理");
  assert.equal(configuration.description, "管理资料和任务边界");
});
