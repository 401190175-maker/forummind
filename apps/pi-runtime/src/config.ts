import { mkdir } from "node:fs/promises";
import { isAbsolute, join, normalize, relative, resolve } from "node:path";

export type RuntimeConfig = {
  host: string;
  port: number;
  runtimeToken: string;
  provider: string;
  model: string;
  apiKey: string;
  baseUrl: string;
  sessionRoot: string;
  runtimeCwd: string;
  agentDir: string;
  controlPlaneUrl: string;
  maxConcurrencyPerGroup: number;
  maxToolCallsPerRun: number;
  maxResultBytes: number;
  maxRequestBytes: number;
  maxSseBuffer: number;
  promptTimeoutMs: number;
};

function positiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value ?? fallback);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function safeRoot(value: string | undefined): string {
  const fallback = join(process.cwd(), ".runtime", "pi-sessions");
  const root = resolve(value || fallback);
  const normalizedRoot = root.toLowerCase();
  if (normalizedRoot.endsWith("/.pi/agent/sessions") || normalizedRoot.endsWith("\\.pi\\agent\\sessions")) {
    throw new Error("PI_SESSION_ROOT cannot use the default Pi session directory");
  }
  return normalize(root);
}

function pathWithin(root: string, candidate: string): boolean {
  const child = resolve(candidate);
  const relativePath = relative(resolve(root), child);
  return relativePath === "" || (!relativePath.startsWith("..") && !isAbsolute(relativePath));
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): RuntimeConfig {
  const sessionRoot = safeRoot(env.PI_SESSION_ROOT);
  const runtimeCwd = resolve(env.PI_RUNTIME_CWD || join(sessionRoot, "runtime-cwd"));
  const agentDir = resolve(env.PI_AGENT_DIR || join(sessionRoot, "agent"));
  if (!pathWithin(sessionRoot, runtimeCwd)) {
    throw new Error("PI_RUNTIME_CWD must be inside PI_SESSION_ROOT");
  }
  if (!pathWithin(sessionRoot, agentDir)) {
    throw new Error("PI_AGENT_DIR must be inside PI_SESSION_ROOT");
  }
  return {
    host: env.PI_RUNTIME_HOST || "127.0.0.1",
    port: positiveInt(env.PI_RUNTIME_PORT, 8010),
    runtimeToken: env.PI_RUNTIME_TOKEN || "",
    provider: env.PI_PROVIDER || "openai-compatible",
    model: env.PI_MODEL || "",
    apiKey: env.PI_API_KEY || "",
    baseUrl: env.PI_BASE_URL || "",
    sessionRoot,
    runtimeCwd,
    agentDir,
    controlPlaneUrl: env.PI_CONTROL_PLANE_URL || "http://127.0.0.1:8000",
    maxConcurrencyPerGroup: positiveInt(env.PI_MAX_CONCURRENCY_PER_GROUP, 2),
    maxToolCallsPerRun: positiveInt(env.PI_MAX_TOOL_CALLS_PER_RUN, 24),
    maxResultBytes: positiveInt(env.PI_MAX_RESULT_BYTES, 64 * 1024),
    maxRequestBytes: positiveInt(env.PI_MAX_REQUEST_BYTES, 256 * 1024),
    maxSseBuffer: positiveInt(env.PI_MAX_SSE_BUFFER, 256),
    promptTimeoutMs: positiveInt(env.PI_PROMPT_TIMEOUT_MS, 300_000),
  };
}

export async function ensureRuntimeDirectories(config: RuntimeConfig): Promise<void> {
  await Promise.all([
    mkdir(config.sessionRoot, { recursive: true }),
    mkdir(config.runtimeCwd, { recursive: true }),
    mkdir(config.agentDir, { recursive: true }),
  ]);
}

export function sessionDirectory(config: RuntimeConfig, scope: {
  groupChatId: string;
  runId: string;
  agentId: string;
}): string {
  const clean = (value: string, field: string): string => {
    const normalized = value.trim();
    if (!normalized || normalized === "." || normalized === ".." || /[\\/]/.test(normalized)) {
      throw new Error(`${field} contains an unsafe path segment`);
    }
    return normalized;
  };
  const candidate = resolve(
    config.sessionRoot,
    clean(scope.groupChatId, "group_chat_id"),
    clean(scope.runId, "run_id"),
    clean(scope.agentId, "agent_id"),
  );
  const root = resolve(config.sessionRoot);
  if (candidate !== root && !candidate.startsWith(`${root}${process.platform === "win32" ? "\\" : "/"}`)) {
    throw new Error("session path escapes PI_SESSION_ROOT");
  }
  if (!isAbsolute(candidate)) throw new Error("session path must be absolute");
  return candidate;
}
