import assert from "node:assert/strict";
import { test } from "node:test";

import { createExperimentStore } from "../lib/stores/experiment-store";

test("selecting the same dataset version twice keeps one exact reference", () => {
  const store = createExperimentStore();
  store.getState().setGroup("group-a");
  store.getState().selectVersion({ dataset_id: "dataset-1", version: 2 });
  store.getState().selectVersion({ dataset_id: "dataset-1", version: 2 });
  assert.deepEqual(store.getState().selectedRefs, [{ dataset_id: "dataset-1", version: 2 }]);
});

test("changing a selected dataset version requires an explicit replacement", () => {
  const store = createExperimentStore();
  store.getState().setGroup("group-a");
  store.getState().selectVersion({ dataset_id: "dataset-1", version: 1 });
  store.getState().selectVersion({ dataset_id: "dataset-1", version: 2 });
  assert.deepEqual(store.getState().selectedRefs, [{ dataset_id: "dataset-1", version: 1 }]);
  store.getState().selectVersion({ dataset_id: "dataset-1", version: 2 }, true);
  assert.deepEqual(store.getState().selectedRefs, [{ dataset_id: "dataset-1", version: 2 }]);
});

test("reconciling server selection keeps the selected older version after a newer version appears", () => {
  const store = createExperimentStore();
  store.getState().setGroup("group-a");
  store.getState().selectVersion({ dataset_id: "dataset-1", version: 1 });
  store.getState().reconcileSelection([{ dataset_id: "dataset-1", version: 1 }]);
  assert.deepEqual(store.getState().selectedRefs, [{ dataset_id: "dataset-1", version: 1 }]);
});
