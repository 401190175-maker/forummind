import assert from "node:assert/strict";
import { test } from "node:test";

import * as selectors from "../components/experiments/selectors";
import { downloadExperimentSourceUrl } from "../lib/api";
import type { ExperimentDataset, SourceRowRef } from "../lib/api";

process.env.NEXT_PUBLIC_API_BASE_URL = "/api";

const refs: SourceRowRef[] = Array.from({ length: 15 }, (_, index) => ({
  dataset_id: "dataset-1",
  dataset_version: 2,
  source_document_id: "source-1",
  row_number: index + 1,
  column_name: "strength",
  source_location: `strength.csv:${index + 1}:strength`,
  data_space: "desensitized_real",
  verification_status: "verified",
  source_ref: `analysis:row-${index + 1}`,
}));

const dataset = {
  rows: [{ row_number: 2, values: { strength: 0 } }],
} as unknown as ExperimentDataset;

test("provenance lookup preserves zero and reports a missing row", () => {
  const find = (selectors as typeof selectors & {
    findSourceRow?: (dataset: ExperimentDataset | null, ref: SourceRowRef) => unknown;
  }).findSourceRow;
  assert.deepEqual(find?.(dataset, refs[1]), { row_number: 2, values: { strength: 0 } });
  assert.equal(find?.(dataset, refs[4]), null);
});

test("provenance refs are progressively revealed in bounded pages", () => {
  const page = (selectors as typeof selectors & {
    sourceRefsForPage?: (items: SourceRowRef[], page: number, pageSize?: number) => SourceRowRef[];
  }).sourceRefsForPage;
  assert.equal(page?.(refs, 0, 12).length, 12);
  assert.equal(page?.(refs, 1, 12).length, 3);
});

test("source download stays server-scoped and does not expose local paths", () => {
  const url = downloadExperimentSourceUrl("group-a", "dataset/1", 2);
  assert.equal(url, "/api/group-chats/group-a/experiment-datasets/dataset%2F1/versions/2/source");
  assert.equal(url.includes("C:\\"), false);
});
