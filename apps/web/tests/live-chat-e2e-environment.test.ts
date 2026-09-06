import assert from "node:assert/strict";
import { test } from "node:test";

import { isolatedE2eApiUrl } from "../../../changes/frontend/真实科研最小闭环/e2e/environment";

test("Task 9 browser tests reject a developer API environment", () => {
  assert.throws(
    () => isolatedE2eApiUrl({ FORUMMIND_E2E_API_PORT: "8000" }),
    /FORUMMIND_E2E_ISOLATED/,
  );
});

test("Task 9 browser tests use the isolated API port assigned by the test config", () => {
  assert.equal(
    isolatedE2eApiUrl({
      FORUMMIND_E2E_ISOLATED: "true",
      FORUMMIND_E2E_API_PORT: "8111",
    }),
    "http://127.0.0.1:8111",
  );
});
