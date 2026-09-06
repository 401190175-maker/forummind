"use client";

import { create } from "zustand";
import { checkHealth } from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";

export type ApiStatus =
  | { kind: "checking" }
  | { kind: "connected"; service: string; environment: string }
  | { kind: "http-error"; status: number }
  | { kind: "missing-config" }
  | { kind: "disconnected" };

type ApiStatusState = {
  status: ApiStatus;
  /** 检查后端 /health 连接状态（页面挂载时调用一次即可）。 */
  check: () => Promise<void>;
};

export const useApiStatusStore = create<ApiStatusState>((set) => ({
  status: { kind: "checking" },
  check: async () => {
    set({ status: { kind: "checking" } });
    try {
      const data = await checkHealth();
      set({
        status: {
          kind: "connected",
          service: data.service,
          environment: data.environment,
        },
      });
    } catch (err) {
      if (err instanceof ApiConfigError) {
        set({ status: { kind: "missing-config" } });
      } else if (err instanceof ApiError && err.status > 0) {
        set({ status: { kind: "http-error", status: err.status } });
      } else {
        set({ status: { kind: "disconnected" } });
      }
    }
  },
}));
