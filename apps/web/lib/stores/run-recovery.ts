export const RUN_STORAGE_KEY = "forummind.runs.v1";

export type RunStorage = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
};

type PersistedRun = string | { run_id: string; event_cursor: number };
type PersistedRuns = Record<string, PersistedRun>;

function readPersistedRuns(storage: RunStorage): PersistedRuns {
  const raw = storage.getItem(RUN_STORAGE_KEY);
  if (!raw) return {};
  try {
    const value = JSON.parse(raw) as unknown;
    return value !== null && typeof value === "object"
      ? (value as PersistedRuns)
      : {};
  } catch {
    return {};
  }
}

export function readPersistedRunId(
  groupChatId: string,
  storage: RunStorage,
): string | null {
  if (!groupChatId) return null;
  try {
    const value = readPersistedRuns(storage)[groupChatId];
    if (typeof value === "string") return value.trim().length > 0 ? value : null;
    return value?.run_id?.trim().length ? value.run_id : null;
  } catch {
    return null;
  }
}

export function savePersistedRunId(
  groupChatId: string,
  runId: string,
  storage: RunStorage,
): void {
  if (!groupChatId || !runId) return;
  try {
    const runs = readPersistedRuns(storage);
    const current = runs[groupChatId];
    runs[groupChatId] = typeof current === "object"
      ? { ...current, run_id: runId }
      : runId;
    storage.setItem(RUN_STORAGE_KEY, JSON.stringify(runs));
  } catch {
    // Browser persistence is an enhancement; a blocked storage mode must not
    // prevent the in-memory run from continuing.
  }
}

export function readPersistedRunCursor(
  groupChatId: string,
  storage: RunStorage,
): number {
  if (!groupChatId) return 0;
  try {
    const value = readPersistedRuns(storage)[groupChatId];
    return typeof value === "object" && Number.isInteger(value.event_cursor) && value.event_cursor >= 0
      ? value.event_cursor
      : 0;
  } catch {
    return 0;
  }
}

export function savePersistedRunCursor(
  groupChatId: string,
  runId: string,
  eventCursor: number,
  storage: RunStorage,
): void {
  if (!groupChatId || !runId || !Number.isInteger(eventCursor) || eventCursor < 0) return;
  try {
    const runs = readPersistedRuns(storage);
    runs[groupChatId] = { run_id: runId, event_cursor: eventCursor };
    storage.setItem(RUN_STORAGE_KEY, JSON.stringify(runs));
  } catch {
    // Browser persistence is an enhancement; a blocked storage mode must not
    // prevent the in-memory run from continuing.
  }
}

export function clearPersistedRunId(
  groupChatId: string,
  storage: RunStorage,
): void {
  if (!groupChatId) return;
  try {
    const runs = readPersistedRuns(storage);
    delete runs[groupChatId];
    storage.setItem(RUN_STORAGE_KEY, JSON.stringify(runs));
  } catch {
    // Ignore storage failures for the same reason as savePersistedRunId.
  }
}
