import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type, type TSchema } from "typebox";
import type { AgentInvocation } from "../contracts.js";
import { toNativeToolName } from "./tool-name-map.js";

export type ToolGatewayRequest = {
  request_id: string;
  name: string;
  arguments: Record<string, unknown>;
  run_id: string;
  group_chat_id: string;
  agent_id: string;
  role: string;
  phase: string;
  cycle: number | null;
  input_refs: string[];
  data_space: string;
  task_id?: string;
  document_scope?: string[];
};

export type ToolGatewayResult = {
  status: "ok" | "denied" | "error" | "limit_exceeded";
  payload: Record<string, unknown>;
  source_refs: string[];
  data_space: string;
  error_code?: string | null;
};

export type ToolGateway = {
  execute(request: ToolGatewayRequest, signal?: AbortSignal): Promise<ToolGatewayResult>;
};

export class HttpToolGateway implements ToolGateway {
  constructor(private readonly baseUrl: string, private readonly token: string) {}

  async execute(request: ToolGatewayRequest, signal?: AbortSignal): Promise<ToolGatewayResult> {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}/internal/runtime/tool-calls`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-ForumMind-Runtime-Token": this.token },
      body: JSON.stringify(request),
      signal,
    });
    if (!response.ok) throw new Error(`ForumMind Tool Gateway rejected request: HTTP ${response.status}`);
    const result = await response.json() as ToolGatewayResult;
    if (!result || typeof result !== "object" || typeof result.status !== "string") {
      throw new Error("ForumMind Tool Gateway returned an invalid result");
    }
    return result;
  }
}

type ToolSpec = {
  canonicalName: string;
  nativeName: string;
  description: string;
  parameters: TSchema;
  dataSpaces: string[];
};

const specs: ToolSpec[] = [
  {
    canonicalName: "memory.query",
    nativeName: "foam_memory_query",
    description: "Query only the current ForumMind synthetic research memory.",
    parameters: Type.Object({ query: Type.String({ minLength: 1 }) }),
    dataSpaces: ["synthetic"],
  },
  {
    canonicalName: "literature.search",
    nativeName: "foam_literature_search",
    description: "Search only the current ForumMind synthetic literature leads.",
    parameters: Type.Object({ query: Type.String({ minLength: 1 }) }),
    dataSpaces: ["synthetic"],
  },
  {
    canonicalName: "experiment.analyze_demo",
    nativeName: "foam_experiment_analyze_demo",
    description: "Analyze the current ForumMind synthetic experiment view.",
    parameters: Type.Object({ metric: Type.Optional(Type.String()) }),
    dataSpaces: ["synthetic"],
  },
  {
    canonicalName: "knowledge.search",
    nativeName: "foam_knowledge_search",
    description: "Search current task-authorized real research documents.",
    parameters: Type.Object({
      query: Type.String({ minLength: 1 }),
      document_ids: Type.Optional(Type.Array(Type.String({ minLength: 1 }))),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 10 })),
    }),
    dataSpaces: ["real", "desensitized_real"],
  },
  {
    canonicalName: "experiment.analyze",
    nativeName: "foam_experiment_analyze",
    description: "Analyze one task-bound immutable experiment dataset version.",
    parameters: Type.Object({
      dataset_id: Type.String({ minLength: 1 }),
      dataset_version: Type.Integer({ minimum: 1 }),
      operation: Type.Union([
        Type.Literal("summary"), Type.Literal("correlation"), Type.Literal("group_mean"),
      ]),
      column_name: Type.String({ minLength: 1 }),
      compare_column: Type.Optional(Type.String({ minLength: 1 })),
      group_by: Type.Optional(Type.String({ minLength: 1 })),
    }),
    dataSpaces: ["real", "desensitized_real"],
  },
];

export function buildForumMindTools(invocation: AgentInvocation, gateway: ToolGateway) {
  const allowed = new Set(invocation.allowed_tools);
  return specs
    .filter((spec) => allowed.has(spec.canonicalName) && spec.dataSpaces.includes(invocation.data_space))
    .map((spec) => defineTool({
      name: spec.nativeName,
      label: `ForumMind ${spec.canonicalName}`,
      description: spec.description,
      promptSnippet: `Use ${spec.nativeName} for governed ${invocation.data_space} read-only research context.`,
      parameters: spec.parameters,
      async execute(toolCallId, params, signal) {
        if (signal?.aborted) throw new Error("tool call aborted");
        const result = await gateway.execute({
          request_id: toolCallId,
          name: spec.canonicalName,
          arguments: params as Record<string, unknown>,
          run_id: invocation.run_id,
          group_chat_id: invocation.group_chat_id,
          agent_id: invocation.agent_id,
          role: invocation.role,
          phase: invocation.phase,
          cycle: invocation.cycle,
          input_refs: [...invocation.input_refs],
          data_space: invocation.data_space,
          task_id: invocation.task_id ?? "",
          document_scope: [...(invocation.document_scope ?? [])],
        }, signal);
        return {
          content: [{
            type: "text" as const,
            text: JSON.stringify({
              ...result.payload,
              status: result.status,
              source_refs: result.source_refs,
              data_space: result.data_space,
              error_code: result.error_code ?? null,
            }),
          }],
          details: {
            status: result.status,
            source_refs: result.source_refs,
            data_space: result.data_space,
            error_code: result.error_code ?? null,
          },
          isError: result.status !== "ok",
        };
      },
    }));
}

export { toNativeToolName };
