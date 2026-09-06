"use client";

import { ArrowLeft, FlaskConical } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  downloadExperimentSourceUrl,
  type AnalysisResult,
  type DatasetVersionRef,
  type ExperimentFieldType,
} from "@/lib/api";
import { useExperimentStore } from "@/lib/stores/experiment-store";
import { AnalysisBuilder } from "./analysis-builder";
import { AnalysisHistory } from "./analysis-history";
import { AnalysisResultView } from "./analysis-result";
import { DatasetList } from "./dataset-list";
import { DatasetPreview } from "./dataset-preview";
import { DatasetUpload } from "./dataset-upload";
import { DatasetVersionDetail } from "./dataset-version-detail";
import { DatasetVersionPicker } from "./dataset-version-picker";
import { ExperimentEmptyState } from "./experiment-empty-state";
import { ProvenanceDetail } from "./provenance-detail";
import { SourceRowTable } from "./source-row-table";
import { experimentRefKey } from "@/lib/stores/experiment-store";

type PanelView = "datasets" | "analysis" | "provenance";

export function ExperimentWorkspacePanel({ groupChatId }: { groupChatId: string }) {
  const group = useExperimentStore((state) => state.groupChatId);
  const datasets = useExperimentStore((state) => state.datasets);
  const versionsByDataset = useExperimentStore((state) => state.versionsByDataset);
  const selectedRefs = useExperimentStore((state) => state.selectedRefs);
  const activeDatasetId = useExperimentStore((state) => state.activeDatasetId);
  const activeVersion = useExperimentStore((state) => state.activeVersion);
  const preview = useExperimentStore((state) => state.preview);
  const requests = useExperimentStore((state) => state.requests);
  const error = useExperimentStore((state) => state.error);
  const analysesByRef = useExperimentStore((state) => state.analysesByRef);
  const setGroup = useExperimentStore((state) => state.setGroup);
  const loadDatasets = useExperimentStore((state) => state.loadDatasets);
  const loadVersions = useExperimentStore((state) => state.loadVersions);
  const selectVersion = useExperimentStore((state) => state.selectVersion);
  const setActiveVersion = useExperimentStore((state) => state.setActiveVersion);
  const previewFileForImport = useExperimentStore((state) => state.previewFileForImport);
  const clearPreview = useExperimentStore((state) => state.clearPreview);
  const importPreview = useExperimentStore((state) => state.importPreview);
  const runAnalysis = useExperimentStore((state) => state.runAnalysis);
  const loadAnalyses = useExperimentStore((state) => state.loadAnalyses);
  const [view, setView] = useState<PanelView>("datasets");
  const [sourceRef, setSourceRef] = useState<AnalysisResult["provenance"][number] | null>(null);

  useEffect(() => {
    if (group !== groupChatId) setGroup(groupChatId);
    void loadDatasets();
  }, [group, groupChatId, loadDatasets, setGroup]);

  const versions = activeDatasetId ? versionsByDataset[activeDatasetId] ?? [] : [];
  const activeDataset = versions.find((item) => item.version === activeVersion) ?? null;
  const selectedRef = selectedRefs.find((ref) => ref.dataset_id === activeDatasetId);
  const analyses = selectedRef ? analysesByRef[experimentRefKey(selectedRef)] ?? [] : [];
  const selectedSourceDataset = sourceRef
    ? (versionsByDataset[sourceRef.dataset_id] ?? []).find((item) => item.version === sourceRef.dataset_version) ?? null
    : null;

  const openDataset = (datasetId: string) => {
    setView("datasets");
    void loadVersions(datasetId);
  };

  const handleVersionSelect = (version: number) => {
    if (!activeDatasetId) return;
    const existing = selectedRefs.find((ref) => ref.dataset_id === activeDatasetId);
    if (existing && existing.version !== version && !window.confirm(`将分析版本从 v${existing.version} 切换到 v${version}？`)) return;
    const ref: DatasetVersionRef = { dataset_id: activeDatasetId, version };
    selectVersion(ref, true);
    setActiveVersion(activeDatasetId, version);
    void loadAnalyses(ref);
  };

  const handleImport = async (sampleSchema: Record<string, ExperimentFieldType>, units: Record<string, string>) => {
    await importPreview({ sampleSchema, units });
  };

  const handleAnalysis = async (spec: { operation: "summary" | "correlation" | "group_mean"; column_name: string; compare_column?: string; group_by?: string }) => {
    if (!selectedRef) return;
    const result = await runAnalysis(selectedRef, spec);
    if (result) setView("analysis");
  };

  const handleOpenAnalysis = (analysis: AnalysisResult) => {
    const ref = { dataset_id: analysis.dataset_id, version: analysis.dataset_version };
    setActiveVersion(ref.dataset_id, ref.version);
    if (!versionsByDataset[ref.dataset_id]) void loadVersions(ref.dataset_id);
    void loadAnalyses(ref);
    setView("analysis");
  };

  const handleSource = (ref: AnalysisResult["provenance"][number]) => {
    setSourceRef(ref);
    setView("provenance");
  };

  return (
    <div className="flex min-h-full flex-col bg-card/95">
      <div className="border-b border-border/70 px-3 pb-3">
        <div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-center gap-2"><span className="flex size-8 shrink-0 items-center justify-center border border-primary/25 bg-primary/10 text-primary"><FlaskConical className="size-4" aria-hidden /></span><div className="min-w-0"><p className="truncate text-sm font-semibold">实验数据</p><p className="mt-0.5 text-[11px] text-muted-foreground">预览 · 版本 · 分析 · 来源</p></div></div><DatasetUpload loading={requests.preview === "loading"} disabled={requests.preview === "loading" || requests.import === "loading"} onFile={(file) => void previewFileForImport(file)} /></div>
        <div className="mt-3 grid grid-cols-3 gap-1 border border-border/70 bg-background/40 p-1" role="tablist" aria-label="实验工作区视图">
          <button type="button" role="tab" aria-selected={view === "datasets"} onClick={() => setView("datasets")} className={`px-1 py-1.5 text-[11px] ${view === "datasets" ? "bg-primary/15 font-medium text-primary" : "text-muted-foreground hover:bg-secondary/60"}`}>数据集</button>
          <button type="button" role="tab" aria-selected={view === "analysis"} disabled={!selectedRef} onClick={() => setView("analysis")} className={`px-1 py-1.5 text-[11px] disabled:opacity-40 ${view === "analysis" ? "bg-primary/15 font-medium text-primary" : "text-muted-foreground hover:bg-secondary/60"}`}>分析</button>
          <button type="button" role="tab" aria-selected={view === "provenance"} disabled={!sourceRef} onClick={() => setView("provenance")} className={`px-1 py-1.5 text-[11px] disabled:opacity-40 ${view === "provenance" ? "bg-primary/15 font-medium text-primary" : "text-muted-foreground hover:bg-secondary/60"}`}>来源</button>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        {error && <p className="border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>}
        {preview && <DatasetPreview preview={preview} busy={requests.import === "loading"} onCancel={clearPreview} onImport={(schema, units) => void handleImport(schema, units)} />}
        {!preview && view === "datasets" && (
          <>
            {datasets.length === 0 && requests.datasets !== "loading" ? <ExperimentEmptyState onUpload={() => document.querySelector<HTMLInputElement>('input[aria-label="选择实验数据文件"]')?.click()} /> : <DatasetList datasets={datasets} selectedRefs={selectedRefs} loading={requests.datasets === "loading"} onOpen={openDataset} onRefresh={() => void loadDatasets()} />}
            {activeDatasetId && versions.length > 0 && <DatasetVersionPicker versions={versions} selected={selectedRef} activeVersion={activeVersion} onSelect={handleVersionSelect} />}
            {activeDataset && <DatasetVersionDetail dataset={activeDataset} downloadUrl={downloadExperimentSourceUrl(groupChatId, activeDataset.dataset_id, activeDataset.version)} />}
          </>
        )}
        {!preview && view === "analysis" && selectedRef && activeDataset && (
          <>
            <button type="button" onClick={() => setView("datasets")} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" aria-hidden />返回版本</button>
            <AnalysisBuilder dataset={activeDataset} busy={requests.analysis === "loading"} onRun={(spec) => void handleAnalysis(spec)} />
            {analyses[0] && <AnalysisResultView result={analyses[0]} onSource={handleSource} />}
            <AnalysisHistory analyses={analyses} onOpen={handleOpenAnalysis} />
          </>
        )}
        {!preview && view === "provenance" && sourceRef && (
          <>
            <ProvenanceDetail dataset={selectedSourceDataset} ref={sourceRef} downloadUrl={downloadExperimentSourceUrl(groupChatId, sourceRef.dataset_id, sourceRef.dataset_version)} onBack={() => setView("analysis")} />
            <SourceRowTable dataset={selectedSourceDataset} refs={[sourceRef]} onSelect={setSourceRef} />
          </>
        )}
        {!preview && view === "analysis" && selectedRef && analyses[0] && <SourceRowTable dataset={activeDataset} refs={analyses[0].provenance} onSelect={handleSource} />}
      </div>
    </div>
  );
}
