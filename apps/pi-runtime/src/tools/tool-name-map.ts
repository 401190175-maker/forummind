export const canonicalToNativeToolName: Readonly<Record<string, string>> = {
  "memory.query": "foam_memory_query",
  "literature.search": "foam_literature_search",
  "experiment.analyze_demo": "foam_experiment_analyze_demo",
  "experiment.analyze": "foam_experiment_analyze",
  "knowledge.search": "foam_knowledge_search",
};

export const nativeToCanonicalToolName: Readonly<Record<string, string>> = Object.fromEntries(
  Object.entries(canonicalToNativeToolName).map(([canonical, native]) => [native, canonical]),
);

export function toNativeToolName(canonicalName: string): string {
  return canonicalToNativeToolName[canonicalName] ?? `foam_${canonicalName.replace(/[^a-zA-Z0-9]+/g, "_")}`;
}

export function toCanonicalToolName(nativeName: string): string {
  return nativeToCanonicalToolName[nativeName] ?? nativeName;
}
