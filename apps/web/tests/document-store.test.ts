import assert from "node:assert/strict";
import { test } from "node:test";

import { documentStatusMeta } from "../lib/stores/document-status.ts";

test("document status mapping keeps processing and failed states visible", () => {
  assert.equal(documentStatusMeta("processing").label, "索引中");
  assert.equal(documentStatusMeta("failed").tone, "error");
  assert.equal(documentStatusMeta("ready").tone, "success");
});
