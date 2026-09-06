/**
 * ForumMind API 客户端层（开发计划 §7.3 契约）。
 *
 * 页面与组件不直接写 fetch，统一通过本模块访问后端。
 * 所有函数只读 NEXT_PUBLIC_API_BASE_URL（无代码级默认值）。
 */
import { ApiConfigError, ApiError } from "./api-errors";

export function apiBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!base) {
    throw new ApiConfigError();
  }
  return base;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const headers = init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...init?.headers };
    res = await fetch(`${apiBaseUrl()}${path}`, {
      headers,
      ...init,
    });
  } catch {
    throw new ApiError(0, "无法连接 API 服务，请确认后端已启动");
  }
  if (!res.ok) {
    let detail: string;
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = formatErrorDetail(body.detail, res.status);
    } catch {
      detail = `HTTP ${res.status}`;
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/**
 * 把后端错误 detail 格式化为可读信息。
 * - string：原样使用。
 * - 数组（FastAPI 422 ValidationError：[{loc, msg, type}, ...]）：
 *   拼接 "loc1.loc2: msg"，多条用 "；" 连接。
 * - 其他：回退 "HTTP {status}"。
 */
function formatErrorDetail(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item !== "object" || item === null) return null;
        const loc = (item as { loc?: unknown }).loc;
        const msg = (item as { msg?: unknown }).msg;
        const locStr = Array.isArray(loc)
          ? loc.filter((p): p is string => typeof p === "string").join(".")
          : "";
        const msgStr = typeof msg === "string" ? msg : "";
        return [locStr, msgStr].filter(Boolean).join(": ");
      })
      .filter((s): s is string => s !== null && s.length > 0);
    if (parts.length > 0) {
      return parts.join("；");
    }
  }
  return `HTTP ${status}`;
}

/* ------------------------------------------------------------------ */
/* 类型（字段与后端 Run API / Group Chat API 对齐）                       */
/* ------------------------------------------------------------------ */

export type RunStep = {
  id: string;
  phase: string;
  kind: string;
  actor: string;
  content: string;
  payload: unknown;
  timestamp: number;
};

export type MeetingEvent = {
  id: string;
  run_id: string;
  actor_id: string;
  actor_role: string;
  kind: string;
  content: string;
  timestamp: number;
  source_refs: string[];
  source: string;
  phase: string;
  sequence: number;
};

export type MemoryEntry = {
  id: string;
  kind: string;
  payload: unknown;
  version: number;
  supersedes: string | null;
  created_at: number;
  object_key: string | null;
  data_space: string;
};

/** Memory 三视图投影（design §4.3）：时间轴 / 版本树 / 证据图谱。 */
export type MemoryViews = {
  timeline: Array<Record<string, unknown>>;
  version_tree: Array<Record<string, unknown>>;
  evidence_graph: {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
  };
};

export type ExperimentPlanView = {
  title: string;
  candidate_explanations: string[];
  controls: string[];
  sample_chain: string;
  measurements: string[];
  branches: string[];
  branch_effects: string[];
  cost_risk: string;
  approval_boundary: {
    option: DecisionOption;
    reason: string;
  } | null;
};

export type ExperimentResultsView = {
  source: string;
  rows: Array<Record<string, unknown>>;
  notes: string;
  validation_summary: string;
  imported_at: number | null;
};

export type HypothesisUpdateView = {
  claim_id: string;
  status: "supported" | "weakened" | "inconclusive" | "posterior" | string;
  reason: string;
  causal_boundary: string;
};

export type ResearchStateChangeView = {
  previous_ref: string | null;
  current_ref: string | null;
  summary: string;
  trigger: string;
  supersedes: boolean;
  preserves_old_version: boolean;
};

export type ExperimentView = {
  data_space: "synthetic";
  phase: string;
  plan: ExperimentPlanView | null;
  results: ExperimentResultsView | null;
  hypothesis_updates: HypothesisUpdateView[];
  research_state_change: ResearchStateChangeView | null;
  boundary_notes: string[];
};

export type RunSnapshot = {
  run_id: string;
  status: string;
  mode: string;
  phase: string;
  cycle: number;
  agent_specs: Array<Record<string, unknown>>;
  runtime_name: string;
  error: string;
  steps: RunStep[];
  memory: MemoryEntry[];
  /** 可选：后端附加的 Memory 三视图投影；缺失时前端从 raw memory 降级。 */
  memory_views?: MemoryViews;
  /** 可选：后端附加的实验视图投影；缺失时前端从 raw steps/memory 降级。 */
  experiment_view?: ExperimentView;
  review_agent_spec: Record<string, unknown>;
  task_context: Record<string, unknown>;
  artifacts: RunArtifact[];
  tool_calls?: Array<Record<string, unknown>>;
};

export type RunArtifact = {
  artifact_id: string;
  run_id: string;
  group_chat_id: string;
  agent_id: string;
  artifact_type: string;
  version?: number;
  source_refs?: string[];
  filename: string;
  content: string;
  data_space: string;
  created_at: number;
  updated_at: number;
};

export type DatasetVersionRef = {
  dataset_id: string;
  version: number;
};

export type ExperimentFieldType = "sample_id" | "number" | "text";

export type ExperimentPreview = {
  filename: string;
  columns: string[];
  inferred_field_types: Record<string, ExperimentFieldType>;
  sample_rows: Array<Record<string, unknown>>;
  validation_findings: Array<Record<string, unknown>>;
};

export type ExperimentDatasetSummary = {
  dataset_id: string;
  latest_version: number;
  filename: string;
  source_sha256: string;
  row_count: number;
  columns: string[];
  created_at: number;
  updated_at: number;
};

export type ExperimentRow = {
  row_number: number;
  values: Record<string, unknown>;
  source_document_id: string;
  source_location: string;
  data_space: string;
  source_mode: "live" | "fixture" | "replay";
  verification_status: "unverified" | "verified" | "fixture" | "unavailable";
};

export type ExperimentDataset = {
  dataset_id: string;
  version: number;
  project_id: string;
  group_chat_id: string;
  source_document_id: string;
  filename: string;
  source_sha256: string;
  sample_schema: Record<string, ExperimentFieldType>;
  units: Record<string, string>;
  conditions: Record<string, unknown>;
  rows: ExperimentRow[];
  data_space: string;
  source_mode: "live" | "fixture" | "replay";
  verification_status: "unverified" | "verified" | "fixture" | "unavailable";
  created_at: number;
  updated_at: number;
};

export type AnalysisOperation = "summary" | "correlation" | "group_mean";

export type AnalysisSpec = {
  operation: AnalysisOperation;
  column_name: string;
  compare_column?: string;
  group_by?: string;
};

export type SourceRowRef = {
  dataset_id: string;
  dataset_version: number;
  source_document_id: string;
  row_number: number;
  column_name: string;
  source_location: string;
  data_space: string;
  verification_status: "unverified" | "verified" | "fixture" | "unavailable";
  source_ref: string;
};

export type AnalysisResult = {
  analysis_id: string;
  dataset_id: string;
  dataset_version: number;
  operation: AnalysisOperation | string;
  column_name: string;
  result: Record<string, unknown>;
  input_refs: SourceRowRef[];
  output_refs: string[];
  provenance: SourceRowRef[];
  data_space: string;
  source_mode: "live" | "fixture" | "replay";
  causal_interpretation_allowed: false;
  warnings: string[];
  created_at: number;
};

export type StartRunResponse = {
  run_id: string;
  status: string;
};

export type ArtifactRecord = {
  artifact_id: string;
  group_chat_id: string;
  run_id: string;
  task_id: string;
  artifact_type: string;
  version: number;
  storage_key: string;
  filename: string;
  mime_type: string;
  source_refs: string[];
  status: string;
  data_space: string;
  created_at: number;
  updated_at: number;
};

export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export type DocumentRecord = {
  document_id: string;
  group_chat_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  storage_key: string;
  data_space: string;
  status: DocumentStatus;
  created_at: number;
  updated_at: number;
};

export type ResearchTaskStatus =
  | "ready"
  | "running"
  | "awaiting_review"
  | "completed"
  | "failed"
  | "cancelled";

export type ResearchTask = {
  task_id: string;
  group_chat_id: string;
  title: string;
  question: string;
  document_ids: string[];
  data_space: string;
  status: ResearchTaskStatus;
  created_at: number;
  updated_at: number;
};

export type CandidateEvidenceRef = {
  source_ref: string;
  chunk_id: string | null;
  document_id: string | null;
  group_chat_id: string;
  data_space: string;
  source_type: "user_uploaded" | "literature" | "experiment";
  verification_status: "pending" | "verified" | "unverified" | "unavailable" | "fixture";
  page_or_location: string;
  char_start: number;
  char_end: number;
  analysis_id: string | null;
  dataset_id: string | null;
  dataset_version: number | null;
  source_filename: string | null;
  source_url: string | null;
};

export type CandidateClaim = {
  candidate_id: string;
  task_id: string;
  run_id: string;
  agent_id: string;
  claim: string;
  evidence_refs: string[];
  evidence: CandidateEvidenceRef[];
  reasoning_summary: string;
  uncertainty: string;
  next_action: string;
  data_space: string;
  status: "candidate" | "approved" | "rejected";
  created_at: number | null;
  updated_at: number | null;
};

/** 对齐后端 GET /agents 返回的 AgentProfile（model_dump(mode="json")）。 */
export type AgentProfile = {
  agent_id: string;
  name: string;
  role: string;
  description: string | null;
  primary_ability: string | null;
  secondary_abilities: string[];
  general_research_abilities: string[];
  allowed_data_spaces: string[];
  allowed_tools: string[];
  forbidden_actions: string | null;
  specialty_domain: string | null;
  knowledge_base_coverage: string | null;
};

export type RuntimeEvent = {
  event_id: string;
  cursor: number;
  session_id?: string;
  invocation_id?: string;
  run_id: string;
  group_chat_id?: string;
  agent_id?: string;
  phase?: string;
  type: string;
  payload: Record<string, unknown>;
  data_space?: string;
  timestamp?: number;
  status?: string;
};

export type RuntimeControlAction = "pause" | "resume" | "abort" | "retry" | "steer" | "follow-up";

export type AgentTestResult = {
  test_id: string;
  agent_id: string;
  status: "ready" | "unavailable" | "failed";
  runtime: string;
  result: string;
  error: string;
  duration_ms: number;
  created_at: number;
};

export type AgentRecord = AgentProfile & {
  enabled: boolean;
  latest_test: AgentTestResult | null;
};

export type AgentsResponse = {
  data_space: string;
  agents: AgentRecord[];
};

export type HealthResponse = {
  status: string;
  service: string;
  environment: string;
};

/** 创建课题组响应最小字段（2.2 向导联调时扩展）。 */
export type CreateGroupChatResponse = {
  group_chat: {
    id: string;
    topic_name: string;
    topic_summary: string;
    data_space: string;
  };
  topic: {
    topic_name: string;
    topic_summary: string;
    project_ref: unknown | null;
    research_question_ref: unknown | null;
    research_state_ref: unknown | null;
  };
  members: Array<{
    id: string;
    group_chat_id: string;
    role: string;
    selection_mode: string;
    display_name: string;
    status: string;
    generate_profile: GenerateProfile | null;
    agent_profile_ref?: { object_type: string; object_id: string } | null;
    configuration_version?: string | null;
  }>;
  initial_messages: Array<{ id: string; group_chat_id: string; content: string }>;
  persistence: string;
  agent_automation: string;
  project_phase: string;
  warnings: string[];
};

/** 智能生成成员的期望配置（对齐后端 GenerateProfile，全可选）。 */
export type GenerateProfile = {
  display_name?: string | null;
  primary_ability?: string | null;
  description?: string | null;
  secondary_abilities?: string[];
  general_research_abilities?: string[];
  allowed_tools?: string[];
  allowed_data_spaces?: string[];
  forbidden_actions?: string | null;
  specialty_domain?: string | null;
  knowledge_base_coverage?: string | null;
};

/** 单个角色的成员选择（对齐后端 RoleMemberSelection：existing 必带 agent_ids，generate 必带 count）。 */
export type RoleMemberSelection = {
  selection_mode: "existing" | "generate";
  agent_ids?: string[];
  count?: number;
  generate_profiles?: GenerateProfile[];
};

/** 按角色分组的成员选择（对齐后端 MemberSelection）。 */
export type MemberSelection = {
  postdoc: RoleMemberSelection;
  phd_student: RoleMemberSelection;
  master_student: RoleMemberSelection;
};

/** 创建课题组请求（2.2 向导填充）。 */
export type CreateGroupChatRequest = {
  topic_name: string;
  topic_summary: string;
  member_selection: MemberSelection;
  data_space?: "synthetic" | "real" | "desensitized_real";
  create_placeholder_tasks?: boolean;
};

/** PI 裁决选项（对齐后端 DecisionRequest 枚举）。 */
export type DecisionOption =
  | "approved"
  | "approved_with_conditions"
  | "returned"
  | "deferred"
  | "terminated";

export type RunMode = "auto" | "live" | "replay";

/* ------------------------------------------------------------------ */
/* demo 消息与任务澄清类型（对齐后端 group_chats/schemas.py DTO）          */
/* ------------------------------------------------------------------ */

/** `@` 对象（后端 MentionTarget，design §4.2）。 */
export type MentionTargetDto = {
  target_type: "all" | "role" | "member";
  target_id: string;
  label: string;
};

/** 创建消息请求（后端 CreateMessageRequest）。 */
export type CreateMessageRequest = {
  content: string;
  mention?: MentionTargetDto | null;
  sender_id?: string | null;
  task_id?: string | null;
  attachment_ids?: string[];
  data_space?: string;
};

/** 聊天消息记录（后端 ChatMessageRecord）。 */
export type ChatMessageRecord = {
  id: string;
  group_chat_id: string;
  sender_type: "user" | "system" | "agent";
  sender_id: string | null;
  content: string;
  mention: MentionTargetDto | null;
  task_id: string | null;
  attachment_ids: string[];
  kind?: string;
  payload?: Record<string, unknown>;
  reply_to_message_id?: string | null;
  created_at: number;
  data_space: string;
};

export type ChatSearchResponse = {
  items: ChatMessageRecord[];
  total: number;
  page: number;
  page_size: number;
};

export type ChatSearchFilters = {
  query?: string;
  senderId?: string;
  dateFrom?: string;
  dateTo?: string;
  attachmentId?: string;
  page?: number;
  pageSize?: number;
};

/** 任务澄清请求（后端 TaskClarificationRequest）。 */
export type TaskClarificationRequest = {
  initial_intent: string;
  mention: MentionTargetDto;
  source_message_id?: string | null;
  dataset_refs?: DatasetVersionRef[];
};

export type TaskClarificationAnswerRequest = {
  answer: string;
  source_message_id?: string | null;
};

export type TaskClarificationTurn = {
  question_id: string;
  question: string;
  answer: string | null;
};

/** 任务澄清响应（后端 TaskClarificationResponse）。 */
export type TaskClarificationResponse = {
  id: string;
  group_chat_id: string;
  status: "awaiting_answer" | "ready_to_assign" | "blocked";
  clarifier: string;
  question_id: string | null;
  question: string | null;
  question_number: number;
  max_questions: 7;
  turns: TaskClarificationTurn[];
  data_space: string;
  dataset_refs: DatasetVersionRef[];
  error?: string;
};

export type FormalTaskContext = {
  clarification_id: string;
  group_chat_id: string;
  initial_intent: string;
  turns: TaskClarificationTurn[];
  topic_name: string;
  topic_summary: string;
  mention: MentionTargetDto;
  clarifier_agent_id: string;
  confirmed_at: number;
  data_space: string;
  dataset_refs: DatasetVersionRef[];
};

export type RuntimeSettings = {
  configured: boolean;
  provider: string;
  base_url: string;
  model: string;
  updated_at: number | null;
};

export type RuntimeSettingsRequest = {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
};

export type MeetingScheduleResponse = {
  group_chat_id: string;
  next_meeting_at: string;
  status: "pending" | "triggering" | "triggered" | "failed";
  run_id: string | null;
  error: string;
  triggered_at: number | null;
  updated_at: number;
};

/* ------------------------------------------------------------------ */
/* API 函数                                                             */
/* ------------------------------------------------------------------ */

/** GET /health —— 连接状态检查。 */
export async function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

/** POST /group-chats —— 创建课题组并初始化课题组群聊。 */
export async function createGroupChat(
  body: CreateGroupChatRequest,
): Promise<CreateGroupChatResponse> {
  return request<CreateGroupChatResponse>("/group-chats", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** POST /group-chats/{id}/runs —— 启动 run（mode=auto|live|replay）。 */
export async function startRun(
  groupChatId: string,
  mode: RunMode = "auto",
  clarificationId?: string,
): Promise<StartRunResponse> {
  return request<StartRunResponse>(`/group-chats/${groupChatId}/runs`, {
    method: "POST",
    body: JSON.stringify({ mode, clarification_id: clarificationId ?? null }),
  });
}

/** GET /runs/{run_id} —— 轮询 run 快照（步骤 + Memory 时间线）。 */
export async function getRun(runId: string): Promise<RunSnapshot> {
  return request<RunSnapshot>(`/runs/${runId}`);
}

export async function controlRun(
  runId: string,
  action: RuntimeControlAction,
  message = "",
): Promise<{ run_id: string; status: string; control_state: string }> {
  return request(`/runs/${runId}/control`, {
    method: "POST",
    body: JSON.stringify({ action, message }),
  });
}

/** POST /group-chats/{id}/runs —— 启动绑定研究任务的真实 Live Run。 */
export async function startLiveRun(
  groupChatId: string,
  taskId: string,
  agentId: string,
): Promise<StartRunResponse> {
  return request<StartRunResponse>(`/group-chats/${groupChatId}/runs`, {
    method: "POST",
    body: JSON.stringify({ mode: "live", task_id: taskId, agent_id: agentId }),
  });
}

/** POST /group-chats/{id}/runs —— 从已确认澄清启动真实 Live Run（浏览器唯一入口）。 */
export async function startClarificationLiveRun(
  groupChatId: string,
  clarificationId: string,
): Promise<StartRunResponse> {
  return request<StartRunResponse>(`/group-chats/${groupChatId}/runs`, {
    method: "POST",
    body: JSON.stringify({ mode: "live", clarification_id: clarificationId }),
  });
}

/** POST /group-chats/{id}/documents —— 上传真实或脱敏资料。 */
export async function uploadDocument(
  groupChatId: string,
  file: File,
  dataSpace?: string,
): Promise<DocumentRecord> {
  const body = new FormData();
  body.append("file", file);
  if (dataSpace) body.append("data_space", dataSpace);
  return request<DocumentRecord>(`/group-chats/${groupChatId}/documents`, {
    method: "POST",
    body,
  });
}

/** GET /group-chats/{id}/documents —— 读取资料状态。 */
export async function listDocuments(groupChatId: string): Promise<DocumentRecord[]> {
  return request<DocumentRecord[]>(`/group-chats/${groupChatId}/documents`);
}

/** POST /group-chats/{id}/documents/{document_id}/index —— 触发解析和 FTS 索引。 */
export async function indexDocument(
  groupChatId: string,
  documentId: string,
): Promise<DocumentRecord> {
  return request<DocumentRecord>(
    `/group-chats/${groupChatId}/documents/${documentId}/index`,
    { method: "POST" },
  );
}

export function downloadDocumentUrl(documentId: string, groupChatId: string): string {
  return `${apiBaseUrl()}/documents/${documentId}/download?group_chat_id=${encodeURIComponent(groupChatId)}`;
}

/** POST /group-chats/{id}/experiment-datasets/preview —— 无写入预览。 */
export async function previewExperimentDataset(
  groupChatId: string,
  file: File,
): Promise<ExperimentPreview> {
  const body = new FormData();
  body.append("file", file);
  return request<ExperimentPreview>(`/group-chats/${groupChatId}/experiment-datasets/preview`, {
    method: "POST",
    body,
  });
}

/** POST /group-chats/{id}/experiment-datasets —— 使用服务端拥有的范围导入。 */
export async function importExperimentDataset(
  groupChatId: string,
  file: File,
  input: {
    sampleSchema: Record<string, ExperimentFieldType>;
    units: Record<string, string>;
    conditions?: Record<string, unknown>;
  },
): Promise<ExperimentDataset> {
  const body = new FormData();
  body.append("file", file);
  body.append("sample_schema", JSON.stringify(input.sampleSchema));
  body.append("units", JSON.stringify(input.units));
  body.append("conditions", JSON.stringify(input.conditions ?? {}));
  return request<ExperimentDataset>(`/group-chats/${groupChatId}/experiment-datasets`, {
    method: "POST",
    body,
  });
}

/** GET /group-chats/{id}/experiment-datasets —— 读取数据集摘要。 */
export async function listExperimentDatasets(
  groupChatId: string,
): Promise<ExperimentDatasetSummary[]> {
  return request<ExperimentDatasetSummary[]>(`/group-chats/${groupChatId}/experiment-datasets`);
}

/** GET /group-chats/{id}/experiment-datasets/{dataset}/versions —— 读取不可变版本。 */
export async function listExperimentDatasetVersions(
  groupChatId: string,
  datasetId: string,
): Promise<ExperimentDataset[]> {
  return request<ExperimentDataset[]>(
    `/group-chats/${groupChatId}/experiment-datasets/${encodeURIComponent(datasetId)}/versions`,
  );
}

/** POST /group-chats/{id}/experiment-datasets/{dataset}/analysis —— 执行白名单分析。 */
export async function analyzeExperimentDataset(
  groupChatId: string,
  datasetId: string,
  version: number,
  spec: AnalysisSpec,
): Promise<AnalysisResult> {
  return request<AnalysisResult>(
    `/group-chats/${groupChatId}/experiment-datasets/${encodeURIComponent(datasetId)}/analysis?version=${version}`,
    { method: "POST", body: JSON.stringify(spec) },
  );
}

/** GET /group-chats/{id}/experiment-datasets/{dataset}/analyses —— 分析历史。 */
export async function listExperimentAnalyses(
  groupChatId: string,
  datasetId: string,
  version: number,
): Promise<AnalysisResult[]> {
  return request<AnalysisResult[]>(
    `/group-chats/${groupChatId}/experiment-datasets/${encodeURIComponent(datasetId)}/analyses?version=${version}`,
  );
}

/** 生成服务端范围内的源文件下载地址，不暴露本地路径。 */
export function downloadExperimentSourceUrl(
  groupChatId: string,
  datasetId: string,
  version: number,
): string {
  return `${apiBaseUrl()}/group-chats/${groupChatId}/experiment-datasets/${encodeURIComponent(datasetId)}/versions/${version}/source`;
}

export function candidateEvidenceHref(
  evidence: CandidateEvidenceRef,
  fallbackGroupChatId: string,
): string | null {
  try {
    const groupChatId = evidence.group_chat_id || fallbackGroupChatId;
    if (evidence.source_type === "user_uploaded") {
      return evidence.document_id ? downloadDocumentUrl(evidence.document_id, groupChatId) : null;
    }
    if (evidence.source_type === "experiment") {
      return evidence.dataset_id && evidence.dataset_version
        ? downloadExperimentSourceUrl(groupChatId, evidence.dataset_id, evidence.dataset_version)
        : null;
    }
    if (!evidence.source_url) return null;
    const url = new URL(evidence.source_url);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

/** POST /group-chats/{id}/tasks —— 创建研究任务。 */
export async function createResearchTask(
  groupChatId: string,
  body: Pick<ResearchTask, "title" | "question" | "document_ids"> & { data_space?: string },
): Promise<ResearchTask> {
  return request<ResearchTask>(`/group-chats/${groupChatId}/tasks`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /group-chats/{id}/tasks —— 读取研究任务。 */
export async function listResearchTasks(groupChatId: string): Promise<ResearchTask[]> {
  return request<ResearchTask[]>(`/group-chats/${groupChatId}/tasks`);
}

/** GET /runs/{id}/candidates —— 读取候选 Claim 和来源元数据。 */
export async function listCandidates(runId: string): Promise<CandidateClaim[]> {
  return request<CandidateClaim[]>(`/runs/${runId}/candidates`);
}

/** POST /runs/{id}/candidates/{candidate_id}/approve —— 批准候选 Claim。 */
export async function approveCandidate(
  runId: string,
  candidateId: string,
  actorId = "user",
): Promise<CandidateClaim> {
  return request<CandidateClaim>(`/runs/${runId}/candidates/${candidateId}/approve`, {
    method: "POST",
    body: JSON.stringify({ actor_id: actorId }),
  });
}

/** POST /runs/{id}/candidates/{candidate_id}/reject —— 拒绝候选 Claim。 */
export async function rejectCandidate(
  runId: string,
  candidateId: string,
  reason: string,
  actorId = "user",
): Promise<CandidateClaim> {
  return request<CandidateClaim>(`/runs/${runId}/candidates/${candidateId}/reject`, {
    method: "POST",
    body: JSON.stringify({ actor_id: actorId, reason }),
  });
}

/** GET /runs/{run_id}/meeting-events —— 读取可恢复的正式组会事件流。 */
export async function getMeetingEvents(runId: string): Promise<MeetingEvent[]> {
  return request<MeetingEvent[]>(`/runs/${runId}/meeting-events`);
}

/** POST /runs/{run_id}/meeting-messages —— 持久化一条 PI 组会插话。 */
export async function appendMeetingMessage(
  runId: string,
  content: string,
): Promise<MeetingEvent> {
  return request<MeetingEvent>(`/runs/${runId}/meeting-messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/** GET /group-chats —— 读取已持久化的课题组创建结果。 */
export async function listGroupChats(query = ""): Promise<CreateGroupChatResponse[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<CreateGroupChatResponse[]>(`/group-chats${suffix}`);
}

/** DELETE /group-chats/{id} —— 删除课题组及其依赖记录。 */
export async function deleteGroupChat(groupChatId: string): Promise<{ deleted: boolean; group_chat_id: string }> {
  return request<{ deleted: boolean; group_chat_id: string }>(`/group-chats/${groupChatId}`, {
    method: "DELETE",
  });
}

/** GET /group-chats/{id} —— 读取一个课题组的服务端事实。 */
export async function getGroupChat(
  groupChatId: string,
): Promise<CreateGroupChatResponse> {
  return request<CreateGroupChatResponse>(`/group-chats/${groupChatId}`);
}

/** GET /group-chats/{id}/meeting-schedule —— 读取服务端组会日程。 */
export async function getMeetingSchedule(
  groupChatId: string,
): Promise<MeetingScheduleResponse | null> {
  return request<MeetingScheduleResponse | null>(
    `/group-chats/${groupChatId}/meeting-schedule`,
  );
}

/** PUT /group-chats/{id}/meeting-schedule —— 保存服务端组会日程。 */
export async function saveMeetingSchedule(
  groupChatId: string,
  nextMeetingAt: string,
): Promise<MeetingScheduleResponse> {
  return request<MeetingScheduleResponse>(
    `/group-chats/${groupChatId}/meeting-schedule`,
    {
      method: "PUT",
      body: JSON.stringify({
        next_meeting_at: new Date(nextMeetingAt).toISOString(),
      }),
    },
  );
}

/** POST /runs/{run_id}/decision —— PI 真交互裁决。 */
export async function decide(
  runId: string,
  option: DecisionOption,
  reason: string,
): Promise<RunSnapshot> {
  return request<RunSnapshot>(`/runs/${runId}/decision`, {
    method: "POST",
    body: JSON.stringify({ option, reason }),
  });
}

/** POST /runs/{run_id}/experiment-results —— 导入结果 → 假设更新。 */
export async function importResults(runId: string): Promise<RunSnapshot> {
  return request<RunSnapshot>(`/runs/${runId}/experiment-results`, {
    method: "POST",
  });
}

/** GET /agents —— demo agent 列表。 */
export async function listAgents(): Promise<AgentsResponse> {
  return request<AgentsResponse>("/agents");
}

/** POST /agents —— 创建可被课题组选择的 Agent Profile。 */
export async function createAgent(profile: AgentProfile): Promise<AgentRecord> {
  return request<AgentRecord>("/agents", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

/** PATCH /agents/{id} —— 更新 Agent Profile。 */
export async function updateAgent(
  agentId: string,
  patch: Partial<AgentProfile> & { enabled?: boolean },
): Promise<AgentRecord> {
  return request<AgentRecord>(`/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** POST /agents/{id}/test —— 执行受控 Agent 测试并返回真实状态。 */
export async function testAgent(
  agentId: string,
  task: string,
): Promise<AgentTestResult> {
  return request<AgentTestResult>(`/agents/${agentId}/test`, {
    method: "POST",
    body: JSON.stringify({ task }),
  });
}

/** POST /group-chats/{id}/messages —— 保存 demo 用户消息（不写正式 Memory）。 */
export async function createGroupChatMessage(
  groupChatId: string,
  body: CreateMessageRequest,
): Promise<ChatMessageRecord> {
  return request<ChatMessageRecord>(`/group-chats/${groupChatId}/messages`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /group-chats/{id}/messages —— 按顺序读取 demo 消息。 */
export async function listGroupChatMessages(
  groupChatId: string,
): Promise<ChatMessageRecord[]> {
  return request<ChatMessageRecord[]>(`/group-chats/${groupChatId}/messages`);
}

/** GET /group-chats/{id}/messages/search —— 服务端 FTS + 条件筛选。 */
export async function searchGroupChatMessages(
  groupChatId: string,
  filters: ChatSearchFilters = {},
): Promise<ChatSearchResponse> {
  const params = new URLSearchParams();
  const values: Array<[string, string | number | undefined]> = [
    ["query", filters.query],
    ["sender_id", filters.senderId],
    ["date_from", filters.dateFrom],
    ["date_to", filters.dateTo],
    ["attachment_id", filters.attachmentId],
    ["page", filters.page],
    ["page_size", filters.pageSize],
  ];
  for (const [key, value] of values) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const suffix = params.toString();
  return request<ChatSearchResponse>(
    `/group-chats/${groupChatId}/messages/search${suffix ? `?${suffix}` : ""}`,
  );
}

/** POST /group-chats/{id}/task-clarifications —— 创建苏格拉底式任务澄清会话。 */
export async function createTaskClarification(
  groupChatId: string,
  body: TaskClarificationRequest,
): Promise<TaskClarificationResponse> {
  return request<TaskClarificationResponse>(
    `/group-chats/${groupChatId}/task-clarifications`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

/** GET /group-chats/{id}/task-clarifications —— 恢复服务端澄清会话。 */
export async function listTaskClarifications(
  groupChatId: string,
): Promise<TaskClarificationResponse[]> {
  return request<TaskClarificationResponse[]>(`/group-chats/${groupChatId}/task-clarifications`);
}

/** POST /group-chats/{id}/task-clarifications/{clarification_id}/answers —— 提交一轮回答。 */
export async function answerTaskClarification(
  groupChatId: string,
  clarificationId: string,
  body: TaskClarificationAnswerRequest,
): Promise<TaskClarificationResponse> {
  return request<TaskClarificationResponse>(
    `/group-chats/${groupChatId}/task-clarifications/${clarificationId}/answers`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

/** POST /group-chats/{id}/task-clarifications/{clarification_id}/formal-task —— 冻结正式任务。 */
export async function createFormalTask(
  groupChatId: string,
  clarificationId: string,
): Promise<FormalTaskContext> {
  return request<FormalTaskContext>(
    `/group-chats/${groupChatId}/task-clarifications/${clarificationId}/formal-task`,
    { method: "POST" },
  );
}

/** PATCH /group-chats/{id}/members/{member_id}/configuration —— 确认生成成员。 */
export async function configureGeneratedMember(
  groupChatId: string,
  memberId: string,
  configuration: GenerateProfile,
): Promise<CreateGroupChatResponse> {
  return request<CreateGroupChatResponse>(
    `/group-chats/${groupChatId}/members/${memberId}/configuration`,
    { method: "PATCH", body: JSON.stringify(configuration) },
  );
}

/** Runtime 设置只返回非敏感状态，不回显 API Key。 */
export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  return request<RuntimeSettings>("/runtime-settings");
}

export async function saveRuntimeSettings(
  settings: RuntimeSettingsRequest,
): Promise<RuntimeSettings> {
  return request<RuntimeSettings>("/runtime-settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export async function clearRuntimeSettings(): Promise<RuntimeSettings> {
  return request<RuntimeSettings>("/runtime-settings", { method: "DELETE" });
}
