import assert from "node:assert/strict";
import { test } from "node:test";

import {
  analysisSpecFor,
  datasetLabel,
  formatFinding,
  selectedDatasetSummary,
  sourceRefLabel,
} from "../components/experiments/selectors";
import type { ExperimentDataset, ExperimentDatasetSummary, SourceRowRef } from "../lib/api";

const summary: ExperimentDatasetSummary = {
  dataset_id: "foam-strength",
  latest_version: 3,
  filename: "strength.csv",
  source_sha256: "a".repeat(64),
  row_count: 12,
  columns: ["sample_id", "strength", "mix"],
  created_at: 1,
  updated_at: 2,
};

test("dataset labels stay user-facing and never expose internal ids", () => {
  assert.equal(datasetLabel(summary), "strength.csv · 12 行 · 最新 v3");
  assert.deepEqual(
    selectedDatasetSummary([summary], [{ dataset_id: "foam-strength", version: 2 }]),
    { count: 1, labels: ["strength.csv · v2"] },
  );
});

test("analysis selectors enforce the three governed operations", () => {
  assert.deepEqual(analysisSpecFor("summary", "strength", "", ""), {
    operation: "summary",
    column_name: "strength",
  });
  assert.equal(analysisSpecFor("correlation", "strength", "strength", ""), null);
  assert.deepEqual(analysisSpecFor("group_mean", "strength", "", "mix"), {
    operation: "group_mean",
    column_name: "strength",
    group_by: "mix",
  });
});

test("validation findings and source refs have readable labels", () => {
  assert.equal(
    formatFinding({ row_number: 4, column_name: "strength", code: "invalid_number" }),
    "第 4 行 · strength：数值格式无效",
  );
  const ref: SourceRowRef = {
    dataset_id: "foam-strength",
    dataset_version: 2,
    source_document_id: "source-1",
    row_number: 4,
    column_name: "strength",
    source_location: "results.csv:4:strength",
    data_space: "desensitized_real",
    verification_status: "unverified",
    source_ref: "analysis:abc",
  };
  assert.equal(sourceRefLabel(ref), "源文件第 4 行 · strength");
});

test("numeric columns are derived from the immutable schema", () => {
  const dataset = {
    sample_schema: { sample_id: "sample_id", strength: "number", mix: "text" },
  } as unknown as ExperimentDataset;
  assert.deepEqual(
    Object.entries(dataset.sample_schema).filter(([, value]) => value === "number").map(([key]) => key),
    ["strength"],
  );
});
