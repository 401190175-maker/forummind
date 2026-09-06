import assert from "node:assert/strict";
import { test } from "node:test";

import { createExperimentStore, type ExperimentApi } from "../lib/stores/experiment-store";
import type { ExperimentDataset, ExperimentDatasetSummary } from "../lib/api";

const dataset = (id: string, latest_version: number): ExperimentDatasetSummary => ({
  dataset_id: id,
  latest_version,
  filename: `${id}.csv`,
  source_sha256: "b".repeat(64),
  row_count: 2,
  columns: ["sample_id", "strength"],
  created_at: 1,
  updated_at: 2,
});

function fakeApi(overrides: Partial<ExperimentApi> = {}): ExperimentApi {
  return {
    preview: async () => { throw new Error("not used"); },
    importDataset: async () => { throw new Error("not used"); },
    listDatasets: async () => [dataset("foam", 2)],
    listVersions: async () => [],
    analyze: async () => { throw new Error("not used"); },
    listAnalyses: async () => [],
    ...overrides,
  };
}

test("switching groups clears datasets and exact version selections", () => {
  const store = createExperimentStore(fakeApi());
  store.getState().setGroup("group-a");
  store.getState().selectVersion({ dataset_id: "foam", version: 1 });
  store.getState().setGroup("group-b");
  assert.equal(store.getState().groupChatId, "group-b");
  assert.deepEqual(store.getState().selectedRefs, []);
  assert.deepEqual(store.getState().datasets, []);
});

test("dataset refresh never silently advances the selected immutable version", async () => {
  const store = createExperimentStore(fakeApi({ listDatasets: async () => [dataset("foam", 3)] }));
  store.getState().setGroup("group-a");
  store.getState().selectVersion({ dataset_id: "foam", version: 1 });
  await store.getState().loadDatasets();
  assert.deepEqual(store.getState().selectedRefs, [{ dataset_id: "foam", version: 1 }]);
  assert.equal(store.getState().datasets[0]?.latest_version, 3);
});

test("a stale dataset response cannot overwrite a newer group state", async () => {
  let resolve: ((value: ExperimentDatasetSummary[]) => void) | undefined;
  const pending = new Promise<ExperimentDatasetSummary[]>((next) => { resolve = next; });
  const store = createExperimentStore(fakeApi({ listDatasets: async () => pending }));
  store.getState().setGroup("group-a");
  const request = store.getState().loadDatasets();
  store.getState().setGroup("group-b");
  resolve?.([dataset("stale", 1)]);
  await request;
  assert.deepEqual(store.getState().datasets, []);
  assert.equal(store.getState().groupChatId, "group-b");
});

test("independent dataset and version requests keep their own request state", async () => {
  let resolveDatasets: ((value: ExperimentDatasetSummary[]) => void) | undefined;
  let resolveVersions: ((value: ExperimentDataset[]) => void) | undefined;
  const datasets = new Promise<ExperimentDatasetSummary[]>((resolve) => { resolveDatasets = resolve; });
  const versions = new Promise<ExperimentDataset[]>((resolve) => { resolveVersions = resolve; });
  const store = createExperimentStore(fakeApi({
    listDatasets: async () => datasets,
    listVersions: async () => versions,
  }));
  store.getState().setGroup("group-a");

  const datasetRequest = store.getState().loadDatasets();
  const versionRequest = store.getState().loadVersions("foam");
  resolveDatasets?.([dataset("foam", 1)]);
  resolveVersions?.([]);
  await Promise.all([datasetRequest, versionRequest]);

  assert.equal(store.getState().requests.datasets, "success");
  assert.equal(store.getState().requests.versions, "success");
  assert.deepEqual(store.getState().datasets, [dataset("foam", 1)]);
});
