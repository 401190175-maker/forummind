import type { FoamSessionManagerLike, PiSdkLike } from "../src/session-factory.js";

export function createFakePiSdk(): PiSdkLike {
  let nextSessionId = 0;
  class FakeLoader {
    constructor(public readonly options: Record<string, unknown>) {}
    async reload(): Promise<void> {}
  }
  const manager = (persisted: boolean, sessionDir = "") => ({
    isPersisted: () => persisted,
    getCwd: () => "C:/forummind/runtime",
    getSessionDir: () => sessionDir,
  });
  return {
    DefaultResourceLoader: FakeLoader,
    SessionManager: {
      inMemory: () => manager(false),
      create: (_cwd: string, sessionDir: string) => manager(true, sessionDir),
    },
    createAgentSession: async (options) => ({
      session: {
        sessionId: `sess-${++nextSessionId}`,
        systemPrompt: "ForumMind Agent",
        dispose: () => undefined,
        abort: async () => undefined,
        sessionManager: options.sessionManager as FoamSessionManagerLike,
      },
    }),
  };
}
