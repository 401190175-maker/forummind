import assert from "node:assert/strict";
import { test } from "node:test";

import * as selectors from "../components/experiments/selectors";
import { createExperimentStore, type ExperimentApi } from "../lib/stores/experiment-store";
import type { ExperimentDataset, ExperimentPreview } from "../lib/api";

const file = new File(["sample_id,strength\na,10\n"], "strength.csv", { type: "text/csv" });

const preview: ExperimentPreview = {
  filename: "strength.csv",
  columns: ["sample_id", "strength"],
  inferred_field_types: { sample_id: "sample_id", strength: "number" },
  sample_rows: [{ sample_id: "a", strength: 10 }],
  validation_findings: [{ row_number: 2, column_name: "strength", code: "invalid_number" }],
};

const importedDataset = {
  dataset_id: "dataset-1",
  version: 1,
  project_id: "group-project:group-a",
  group_chat_id: "group-a",
  source_document_id: "source-1",
  filename: "strength.csv",
  source_sha256: "a".repeat(64),
  sample_schema: { sample_id: "sample_id", strength: "number" },
  units: { strength: "MPa" },
  conditions: {},
  rows: [],
  data_space: "desensitized_real",
  source_mode: "live",
  verification_status: "verified",
  created_at: 1,
  updated_at: 1,
} as unknown as ExperimentDataset;

function api(overrides: Partial<ExperimentApi> = {}): ExperimentApi {
  return {
    preview: async () => preview,
    importDataset: async () => importedDataset,
    listDatasets: async () => [],
    listVersions: async () => [],
    analyze: async () => { throw new Error("unused"); },
    listAnalyses: async () => [],
    ...overrides,
  };
}

test("experiment upload accepts only CSV and XLSX filenames", () => {
  const isSupported = (selectors as typeof selectors & {
    isSupportedExperimentFileName?: (name: string) => boolean;
  }).isSupportedExperimentFileName;
  assert.equal(isSupported?.("strength.csv"), true);
  assert.equal(isSupported?.("strength.xlsx"), true);
  assert.equal(isSupported?.("notes.pdf"), false);
});

test("preview preserves validation findings and cancel creates no dataset", async () => {
  let imports = 0;
  const store = createExperimentStore(api({
    importDataset: async () => {
      imports += 1;
      return importedDataset;
    },
  }));
  store.getState().setGroup("group-a");
  await store.getState().previewFileForImport(file);

  assert.deepEqual(store.getState().preview?.validation_findings, preview.validation_findings);
  store.getState().clearPreview();
  assert.equal(store.getState().preview, null);
  assert.equal(store.getState().previewFile, null);
  assert.equal(imports, 0);
});

test("duplicate import clicks submit exactly once while the first import is pending", async () => {
  let release: ((dataset: ExperimentDataset) => void) | undefined;
  let imports = 0;
  const pending = new Promise<ExperimentDataset>((resolve) => { release = resolve; });
  const store = createExperimentStore(api({
    importDataset: async () => {
      imports += 1;
      return pending;
    },
  }));
  store.getState().setGroup("group-a");
  await store.getState().previewFileForImport(file);

  const first = store.getState().importPreview({
    sampleSchema: preview.inferred_field_types,
    units: { strength: "MPa" },
  });
  const second = store.getState().importPreview({
    sampleSchema: preview.inferred_field_types,
    units: { strength: "MPa" },
  });
  const secondResult = await Promise.race([
    second,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), 50)),
  ]);
  assert.equal(secondResult, null);
  assert.equal(imports, 1);
  release?.(importedDataset);
  assert.equal(await first, importedDataset);
});

test("a failed preview can be retried with the same file", async () => {
  let attempts = 0;
  const store = createExperimentStore(api({
    preview: async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("preview unavailable");
      return preview;
    },
  }));
  store.getState().setGroup("group-a");
  await store.getState().previewFileForImport(file);
  assert.equal(store.getState().requests.preview, "error");
  await store.getState().previewFileForImport(file);
  assert.equal(store.getState().requests.preview, "success");
  assert.equal(store.getState().preview?.filename, "strength.csv");
});
