import assert from "node:assert/strict";
import { test } from "node:test";

import * as selectors from "../components/experiments/selectors";
import type { AnalysisResult, ExperimentDataset } from "../lib/api";

const result = (analysis_id: string, created_at: number): AnalysisResult => ({
  analysis_id,
  dataset_id: "dataset-1",
  dataset_version: 1,
  operation: "summary",
  column_name: "strength",
  result: { mean: 0, count: 0, missing: null },
  input_refs: [],
  output_refs: [],
  provenance: [],
  data_space: "desensitized_real",
  source_mode: "live",
  causal_interpretation_allowed: false,
  warnings: [],
  created_at,
});

test("analysis result formatting preserves zero and null values", () => {
  assert.equal(selectors.displayResultValue(0), "0");
  assert.equal(selectors.displayResultValue(null), "暂无");
  assert.equal(selectors.displayResultValue(false), "false");
});

test("analysis history is ordered newest first", () => {
  const sort = (selectors as typeof selectors & {
    sortAnalysesByCreatedAt?: (items: AnalysisResult[]) => AnalysisResult[];
  }).sortAnalysesByCreatedAt;
  assert.deepEqual(
    sort?.([result("old", 10), result("new", 20)]).map((item) => item.analysis_id),
    ["new", "old"],
  );
});

test("analysis controls discard columns that are absent after switching dataset versions", () => {
  const dataset = {
    sample_schema: { sample_id: "sample_id", temperature: "number", batch: "text" },
  } as Pick<ExperimentDataset, "sample_schema">;

  assert.deepEqual(
    selectors.normalizeAnalysisSelection(dataset, {
      column: "strength",
      compare: "pressure",
      groupBy: "old_batch",
    }),
    { column: "temperature", compare: "", groupBy: "sample_id" },
  );
});
