import assert from "node:assert/strict";
import { test } from "node:test";

import { selectedDatasetSummary } from "../components/experiments/selectors";

test("selected experiment summary is isolated to the active group dataset list", () => {
  const groupA = [{
    dataset_id: "group-a-dataset",
    latest_version: 2,
    filename: "group-a.csv",
    source_sha256: "a".repeat(64),
    row_count: 3,
    columns: ["sample_id", "strength"],
    created_at: 1,
    updated_at: 2,
  }];

  assert.deepEqual(
    selectedDatasetSummary(groupA, [{ dataset_id: "group-a-dataset", version: 1 }]),
    { count: 1, labels: ["group-a.csv · v1"] },
  );
  assert.deepEqual(
    selectedDatasetSummary([], [{ dataset_id: "group-a-dataset", version: 1 }]),
    { count: 1, labels: ["数据集 · v1"] },
  );
});
