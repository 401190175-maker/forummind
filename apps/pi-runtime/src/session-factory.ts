import {
  ensureRuntimeDirectories,
  loadConfig,
  sessionDirectory,
  type RuntimeConfig,
} from "./config.js";
import type { AgentInvocation } from "./contracts.js";
import { ForumMindModelRuntime, type ModelRuntimeLike } from "./model-runtime.js";
import { buildForumMindSystemPrompt } from "./system-prompt.js";

export type FoamSessionManagerLike = {
  isPersisted(): boolean;
  getCwd(): string;
  getSessionDir?(): string;
};

export type FoamPiSessionLike = {
  sessionId: string;
  sessionFile?: string;
  sessionManager: FoamSessionManagerLike;
  systemPrompt: string;
  prompt?(text: string): Promise<void>;
  steer?(text: string): Promise<void>;
  followUp?(text: string): Promise<void>;
  abort?(): Promise<void>;
  dispose(): void;
  subscribe?(listener: (event: unknown) => void): () => void;
};

export type PiSdkLike = {
  DefaultResourceLoader: new (options: Record<string, unknown>) => {
    reload(): Promise<void>;
  };
  SessionManager: {
    inMemory(cwd: string): FoamSessionManagerLike;
    create(cwd: string, sessionDir: string): FoamSessionManagerLike;
  };
  createAgentSession(options: Record<string, unknown>): Promise<{
    session: FoamPiSessionLike;
    modelFallbackMessage?: string;
  }>;
};

export type ToolFactory = (invocation: AgentInvocation) => {
  tools: unknown[];
  activeToolNames: string[];
};

export type SessionFactoryOptions = {
  sdk?: PiSdkLike;
  storage?: "memory" | "persistent";
  config?: RuntimeConfig;
  modelRuntime?: ModelRuntimeLike;
  toolFactory?: ToolFactory;
};

export type ManagedSession = {
  sessionId: string;
  sessionFile?: string;
  sessionManager: FoamSessionManagerLike;
  session: FoamPiSessionLike;
  systemPrompt: string;
  activeToolNames: string[];
  modelFallbackMessage?: string;
};

export function nativeToolName(canonicalName: string): string {
  const names: Record<string, string> = {
    "memory.query": "foam_memory_query",
    "literature.search": "foam_literature_search",
    "experiment.analyze": "foam_experiment_analyze",
    "knowledge.query": "foam_knowledge_query",
  };
  return names[canonicalName] || `foam_${canonicalName.replace(/[^a-zA-Z0-9]+/g, "_")}`;
}

export async function createForumMindSession(
  invocation: AgentInvocation,
  options: SessionFactoryOptions = {},
): Promise<ManagedSession> {
  const config = options.config ?? loadConfig();
  await ensureRuntimeDirectories(config);
  const sdk = options.sdk ?? await loadDefaultPiSdk();
  const loader = new sdk.DefaultResourceLoader({
    cwd: config.runtimeCwd,
    agentDir: config.agentDir,
    systemPromptOverride: () => buildForumMindSystemPrompt(invocation),
    appendSystemPromptOverride: () => [],
    noContextFiles: true,
    noSkills: true,
    noExtensions: true,
  });
  await loader.reload();

  const sessionManager = options.storage === "persistent"
    ? sdk.SessionManager.create(
        config.runtimeCwd,
        sessionDirectory(config, {
          groupChatId: invocation.group_chat_id,
          runId: invocation.run_id,
          agentId: invocation.agent_id,
        }),
      )
    : sdk.SessionManager.inMemory(config.runtimeCwd);
  const toolSet = options.toolFactory?.(invocation) ?? {
    tools: [],
    activeToolNames: invocation.allowed_tools.map(nativeToolName),
  };
  const modelRuntime = options.modelRuntime ?? new ForumMindModelRuntime(config);
  const model = await modelRuntime.resolve(invocation);
  const sdkModelRuntime = modelRuntime.getRuntime
    ? await modelRuntime.getRuntime()
    : undefined;
  const result = await sdk.createAgentSession({
    cwd: config.runtimeCwd,
    agentDir: config.agentDir,
    resourceLoader: loader,
    sessionManager,
    customTools: toolSet.tools,
    tools: toolSet.activeToolNames,
    noTools: toolSet.activeToolNames.length === 0 ? "all" : undefined,
    model,
    ...(sdkModelRuntime ? { modelRuntime: sdkModelRuntime } : {}),
  });
  return {
    sessionId: result.session.sessionId,
    sessionFile: result.session.sessionFile,
    sessionManager,
    session: result.session,
    systemPrompt: result.session.systemPrompt,
    activeToolNames: toolSet.activeToolNames,
    modelFallbackMessage: result.modelFallbackMessage,
  };
}

async function loadDefaultPiSdk(): Promise<PiSdkLike> {
  const sdk = await import("@earendil-works/pi-coding-agent");
  return {
    DefaultResourceLoader: sdk.DefaultResourceLoader as unknown as PiSdkLike["DefaultResourceLoader"],
    SessionManager: sdk.SessionManager as unknown as PiSdkLike["SessionManager"],
    createAgentSession: sdk.createAgentSession as unknown as PiSdkLike["createAgentSession"],
  };
}
