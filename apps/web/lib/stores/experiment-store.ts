"use client";

import { create } from "zustand";

import {
  analyzeExperimentDataset,
  importExperimentDataset,
  listExperimentAnalyses,
  listExperimentDatasetVersions,
  listExperimentDatasets,
  previewExperimentDataset,
  type AnalysisResult,
  type AnalysisSpec,
  type DatasetVersionRef,
  type ExperimentDataset,
  type ExperimentDatasetSummary,
  type ExperimentFieldType,
  type ExperimentPreview,
} from "@/lib/api";
import { isSupportedExperimentFileName } from "@/components/experiments/selectors";

export type ExperimentRequestKey = "datasets" | "versions" | "preview" | "import" | "analysis";
export type ExperimentRequestState = "idle" | "loading" | "success" | "error";

export type ExperimentImportInput = {
  sampleSchema: Record<string, ExperimentFieldType>;
  units: Record<string, string>;
  conditions?: Record<string, unknown>;
};

export type ExperimentApi = {
  preview: (groupChatId: string, file: File) => Promise<ExperimentPreview>;
  importDataset: (
    groupChatId: string,
    file: File,
    input: ExperimentImportInput,
  ) => Promise<ExperimentDataset>;
  listDatasets: (groupChatId: string) => Promise<ExperimentDatasetSummary[]>;
  listVersions: (groupChatId: string, datasetId: string) => Promise<ExperimentDataset[]>;
  analyze: (
    groupChatId: string,
    datasetId: string,
    version: number,
    spec: AnalysisSpec,
  ) => Promise<AnalysisResult>;
  listAnalyses: (groupChatId: string, datasetId: string, version: number) => Promise<AnalysisResult[]>;
};

const defaultApi: ExperimentApi = {
  preview: previewExperimentDataset,
  importDataset: importExperimentDataset,
  listDatasets: listExperimentDatasets,
  listVersions: listExperimentDatasetVersions,
  analyze: analyzeExperimentDataset,
  listAnalyses: listExperimentAnalyses,
};

type ExperimentStore = {
  groupChatId: string | null;
  datasets: ExperimentDatasetSummary[];
  versionsByDataset: Record<string, ExperimentDataset[]>;
  selectedRefs: DatasetVersionRef[];
  activeDatasetId: string | null;
  activeVersion: number | null;
  preview: ExperimentPreview | null;
  previewFile: File | null;
  analysesByRef: Record<string, AnalysisResult[]>;
  requests: Record<ExperimentRequestKey, ExperimentRequestState>;
  error: string | null;
  setGroup: (groupChatId: string) => void;
  loadDatasets: () => Promise<void>;
  loadVersions: (datasetId: string) => Promise<void>;
  loadVersionDetails: (datasetId: string) => Promise<void>;
  selectVersion: (ref: DatasetVersionRef, replace?: boolean) => void;
  reconcileSelection: (refs: DatasetVersionRef[]) => void;
  clearSelection: (datasetId: string) => void;
  setActiveVersion: (datasetId: string, version: number) => void;
  previewFileForImport: (file: File) => Promise<void>;
  clearPreview: () => void;
  importPreview: (input: ExperimentImportInput) => Promise<ExperimentDataset | null>;
  runAnalysis: (ref: DatasetVersionRef, spec: AnalysisSpec) => Promise<AnalysisResult | null>;
  loadAnalyses: (ref: DatasetVersionRef) => Promise<void>;
  reset: () => void;
};

const initialRequests = (): Record<ExperimentRequestKey, ExperimentRequestState> => ({
  datasets: "idle",
  versions: "idle",
  preview: "idle",
  import: "idle",
  analysis: "idle",
});

const refKey = (ref: DatasetVersionRef) => `${ref.dataset_id}@${ref.version}`;

function readableError(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "实验数据请求失败，请稍后重试";
}

export function createExperimentStore(api: ExperimentApi = defaultApi) {
  let requestGeneration = 0;
  const requestTokens = new Map<string, number>();

  const beginRequest = (key: string) => {
    const token = (requestTokens.get(key) ?? 0) + 1;
    requestTokens.set(key, token);
    return { generation: requestGeneration, token };
  };

  const isCurrentRequest = (
    request: { generation: number; token: number },
    key: string,
    groupChatId: string,
    getGroupChatId: () => string | null,
  ) => (
    request.generation === requestGeneration
    && request.token === requestTokens.get(key)
    && getGroupChatId() === groupChatId
  );

  return create<ExperimentStore>((set, get) => ({
    groupChatId: null,
    datasets: [],
    versionsByDataset: {},
    selectedRefs: [],
    activeDatasetId: null,
    activeVersion: null,
    preview: null,
    previewFile: null,
    analysesByRef: {},
    requests: initialRequests(),
    error: null,

    setGroup: (groupChatId) => {
      if (get().groupChatId === groupChatId) return;
      requestGeneration += 1;
      set({
        groupChatId,
        datasets: [],
        versionsByDataset: {},
        selectedRefs: [],
        activeDatasetId: null,
        activeVersion: null,
        preview: null,
        previewFile: null,
        analysesByRef: {},
        requests: initialRequests(),
        error: null,
      });
    },

    loadDatasets: async () => {
      const groupChatId = get().groupChatId;
      if (!groupChatId) return;
      const key = "datasets";
      const request = beginRequest(key);
      set((state) => ({ requests: { ...state.requests, datasets: "loading" }, error: null }));
      try {
        const datasets = await api.listDatasets(groupChatId);
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          datasets,
          requests: { ...state.requests, datasets: "success" },
        }));
      } catch (error) {
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          requests: { ...state.requests, datasets: "error" },
          error: readableError(error),
        }));
      }
    },

    loadVersions: async (datasetId) => {
      const groupChatId = get().groupChatId;
      if (!groupChatId) return;
      const key = `versions:${datasetId}`;
      const request = beginRequest(key);
      const selectedVersion = get().selectedRefs.find((ref) => ref.dataset_id === datasetId)?.version ?? null;
      set((state) => ({
        activeDatasetId: datasetId,
        activeVersion: selectedVersion,
        requests: { ...state.requests, versions: "loading" },
        error: null,
      }));
      try {
        const versions = await api.listVersions(groupChatId, datasetId);
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          versionsByDataset: { ...state.versionsByDataset, [datasetId]: versions },
          requests: { ...state.requests, versions: "success" },
        }));
      } catch (error) {
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          requests: { ...state.requests, versions: "error" },
          error: readableError(error),
        }));
      }
    },

    loadVersionDetails: async (datasetId) => {
      const groupChatId = get().groupChatId;
      if (!groupChatId) return;
      const key = `versions:${datasetId}`;
      const request = beginRequest(key);
      set((state) => ({ requests: { ...state.requests, versions: "loading" }, error: null }));
      try {
        const versions = await api.listVersions(groupChatId, datasetId);
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          versionsByDataset: { ...state.versionsByDataset, [datasetId]: versions },
          requests: { ...state.requests, versions: "success" },
        }));
      } catch (error) {
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          requests: { ...state.requests, versions: "error" },
          error: readableError(error),
        }));
      }
    },

    selectVersion: (ref, replace = false) => {
      set((state) => {
        const sameDataset = state.selectedRefs.find((item) => item.dataset_id === ref.dataset_id);
        if (sameDataset && sameDataset.version !== ref.version && !replace) return state;
        const selectedRefs = state.selectedRefs.filter((item) => item.dataset_id !== ref.dataset_id);
        return {
          selectedRefs: [...selectedRefs, ref],
          activeDatasetId: ref.dataset_id,
          activeVersion: ref.version,
        };
      });
    },

    reconcileSelection: (refs) => {
      set({
        selectedRefs: refs.filter(
          (ref, index, all) =>
            ref.dataset_id.trim().length > 0 &&
            ref.version >= 1 &&
            all.findIndex((candidate) => candidate.dataset_id === ref.dataset_id) === index,
        ),
      });
    },

    clearSelection: (datasetId) => {
      set((state) => ({
        selectedRefs: state.selectedRefs.filter((ref) => ref.dataset_id !== datasetId),
        activeDatasetId: state.activeDatasetId === datasetId ? null : state.activeDatasetId,
        activeVersion: state.activeDatasetId === datasetId ? null : state.activeVersion,
      }));
    },

    setActiveVersion: (datasetId, version) => set({ activeDatasetId: datasetId, activeVersion: version }),

    previewFileForImport: async (file) => {
      const groupChatId = get().groupChatId;
      if (!groupChatId) return;
      if (!isSupportedExperimentFileName(file.name)) {
        set((state) => ({
          preview: null,
          previewFile: null,
          requests: { ...state.requests, preview: "error" },
          error: "仅支持 CSV 或 XLSX 文件",
        }));
        return;
      }
      if (get().requests.preview === "loading") return;
      const key = "preview";
      const request = beginRequest(key);
      set((state) => ({
        previewFile: file,
        preview: null,
        requests: { ...state.requests, preview: "loading" },
        error: null,
      }));
      try {
        const preview = await api.preview(groupChatId, file);
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({ preview, requests: { ...state.requests, preview: "success" } }));
      } catch (error) {
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          requests: { ...state.requests, preview: "error" },
          error: readableError(error),
        }));
      }
    },

    clearPreview: () => set({ preview: null, previewFile: null, error: null }),

    importPreview: async (input) => {
      const groupChatId = get().groupChatId;
      const file = get().previewFile;
      if (!groupChatId || !file || !get().preview) return null;
      if (get().requests.import === "loading") return null;
      const key = "import";
      const request = beginRequest(key);
      set((state) => ({ requests: { ...state.requests, import: "loading" }, error: null }));
      try {
        const dataset = await api.importDataset(groupChatId, file, input);
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return null;
        set((state) => ({
          preview: null,
          previewFile: null,
          requests: { ...state.requests, import: "success" },
        }));
        await get().loadDatasets();
        return dataset;
      } catch (error) {
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return null;
        set((state) => ({
          requests: { ...state.requests, import: "error" },
          error: readableError(error),
        }));
        return null;
      }
    },

    runAnalysis: async (ref, spec) => {
      const groupChatId = get().groupChatId;
      if (!groupChatId) return null;
      if (get().requests.analysis === "loading") return null;
      const key = `analysis:${refKey(ref)}`;
      const request = beginRequest(key);
      set((state) => ({ requests: { ...state.requests, analysis: "loading" }, error: null }));
      try {
        const result = await api.analyze(groupChatId, ref.dataset_id, ref.version, spec);
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return null;
        const refKeyValue = refKey(ref);
        set((state) => ({
          analysesByRef: { ...state.analysesByRef, [refKeyValue]: [result, ...(state.analysesByRef[refKeyValue] ?? [])] },
          requests: { ...state.requests, analysis: "success" },
        }));
        return result;
      } catch (error) {
        if (!isCurrentRequest(request, key, groupChatId, () => get().groupChatId)) return null;
        set((state) => ({
          requests: { ...state.requests, analysis: "error" },
          error: readableError(error),
        }));
        return null;
      }
    },

    loadAnalyses: async (ref) => {
      const groupChatId = get().groupChatId;
      if (!groupChatId) return;
      const key = refKey(ref);
      const requestKey = `analysis:${key}`;
      const request = beginRequest(requestKey);
      set((state) => ({ requests: { ...state.requests, analysis: "loading" }, error: null }));
      try {
        const analyses = await api.listAnalyses(groupChatId, ref.dataset_id, ref.version);
        if (!isCurrentRequest(request, requestKey, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          analysesByRef: { ...state.analysesByRef, [key]: analyses },
          requests: { ...state.requests, analysis: "success" },
        }));
      } catch (error) {
        if (!isCurrentRequest(request, requestKey, groupChatId, () => get().groupChatId)) return;
        set((state) => ({
          requests: { ...state.requests, analysis: "error" },
          error: readableError(error),
        }));
      }
    },

    reset: () => {
      requestGeneration += 1;
      set({
        groupChatId: null,
        datasets: [],
        versionsByDataset: {},
        selectedRefs: [],
        activeDatasetId: null,
        activeVersion: null,
        preview: null,
        previewFile: null,
        analysesByRef: {},
        requests: initialRequests(),
        error: null,
      });
    },
  }));
}

export const useExperimentStore = createExperimentStore();

export function experimentRefKey(ref: DatasetVersionRef): string {
  return refKey(ref);
}
