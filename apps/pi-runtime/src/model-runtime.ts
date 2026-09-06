import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import type { AgentInvocation } from "./contracts.js";
import type { RuntimeConfig } from "./config.js";

export type ModelRuntimeLike = {
  resolve(invocation: AgentInvocation): Promise<unknown>;
  getRuntime?(): Promise<unknown>;
};

export class ForumMindModelRuntime implements ModelRuntimeLike {
  private runtimePromise?: Promise<ModelRuntime>;

  constructor(private readonly config: RuntimeConfig) {}

  async resolve(_invocation: AgentInvocation): Promise<unknown> {
    if (!this.config.model) return undefined;
    const runtime = await this.runtime();
    const model = runtime.getModel(this.config.provider, this.config.model);
    if (!model) {
      throw new Error(`configured Pi model is unavailable: ${this.config.provider}/${this.config.model}`);
    }
    return model;
  }

  async getRuntime(): Promise<ModelRuntime> {
    return this.runtime();
  }

  private runtime(): Promise<ModelRuntime> {
    this.runtimePromise ??= this.createRuntime();
    return this.runtimePromise;
  }

  async dispose(): Promise<void> {
    await this.runtimePromise?.catch(() => undefined);
    await Promise.all([
      rm(join(this.config.agentDir, "auth.json"), { force: true }),
      rm(join(this.config.agentDir, "models.json"), { force: true }),
    ]);
    this.runtimePromise = undefined;
  }

  private async createRuntime(): Promise<ModelRuntime> {
    await mkdir(this.config.agentDir, { recursive: true });
    const modelsPath = join(this.config.agentDir, "models.json");
    await writeFile(
      modelsPath,
      JSON.stringify({
        providers: {
          [this.config.provider]: {
            baseUrl: this.config.baseUrl,
            api: "openai-completions",
            models: [{ id: this.config.model, input: ["text"], reasoning: false }],
          },
        },
      }),
      { encoding: "utf8", mode: 0o600 },
    );
    const runtime = await ModelRuntime.create({
      authPath: join(this.config.agentDir, "auth.json"),
      modelsPath,
      allowModelNetwork: false,
    });
    if (this.config.apiKey) {
      await runtime.setRuntimeApiKey(this.config.provider, this.config.apiKey);
    }
    return runtime;
  }
}
