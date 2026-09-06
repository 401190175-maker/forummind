"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { CalendarDays, FileText, FlaskConical, Search, UsersRound, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useGroupChatStore,
  recordFromResponse,
  type GroupChatRecord,
} from "@/lib/stores/group-chat-store";
import { toChatRunEvent, useRunStore } from "@/lib/stores/run-store";
import { useDocumentStore } from "@/lib/stores/document-store";
import {
  getGroupChat,
  getMeetingSchedule,
  saveMeetingSchedule,
  createGroupChatMessage,
  createTaskClarification,
  answerTaskClarification,
  configureGeneratedMember,
  listTaskClarifications,
  listGroupChatMessages,
  type ChatMessageRecord,
  type MentionTargetDto,
  type RunArtifact,
} from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import { ChatComposer } from "@/components/group-chat/chat-composer";
import { ChatTranscript } from "@/components/group-chat/chat-transcript";
import { ChatSearchPanel } from "@/components/group-chat/chat-search-panel";
import { ArtifactPanel } from "@/components/group-chat/artifact-panel";
import { MemberPanel } from "@/components/group-chat/member-panel";
import {
  toTimelineItem,
  type ChatTimelineItem,
  type TimelineMember,
} from "@/components/group-chat/chat-types";
import {
  mentionTargetsForActiveMembers,
  pendingClarificationFromHistory,
  type PendingClarification,
} from "@/components/group-chat/live-chat-state";
import { submitLiveChatDraft } from "@/lib/live-chat-submit";
import { useExperimentStore } from "@/lib/stores/experiment-store";
import { selectedDatasetSummary } from "@/components/experiments/selectors";
import { ExperimentWorkspacePanel } from "@/components/experiments/experiment-workspace-panel";
import type { ComposerDraft, MentionTarget } from "@/components/group-chat/types";

type DrawerKind = "artifacts" | "members" | "search" | "experiments" | null;

const EMPTY_ARTIFACTS: RunArtifact[] = [];
const TERMINAL_RUN_STATUSES = new Set(["awaiting_review", "completed", "failed", "cancelled"]);

function dateTimeInputValue(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function readableError(err: unknown): string {
  if (err instanceof ApiConfigError || err instanceof ApiError) return err.message;
  return "请求失败，请稍后重试";
}

export default function GroupChatPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const hydrated = useGroupChatStore((s) => s.hydrated);
  const hydrate = useGroupChatStore((s) => s.hydrate);
  const upsertRecord = useGroupChatStore((s) => s.set);
  const updateMeetingSchedule = useGroupChatStore((s) => s.updateMeetingSchedule);
  const removeCachedGroupChat = useGroupChatStore((s) => s.removeCachedGroupChat);
  const startClarificationLive = useRunStore((s) => s.startClarificationLive);
  const resumeRun = useRunStore((s) => s.resume);
  const activeRunId = useRunStore((s) => s.runId);
  const activeRunGroupChatId = useRunStore((s) => s.runGroupChatId);
  const activeRunStatus = useRunStore((s) => s.snapshot?.status ?? "");
  const runtimeEvents = useRunStore((s) => s.runtimeEvents);
  const artifacts = useRunStore((s) => s.snapshot?.artifacts ?? EMPTY_ARTIFACTS);
  const upload = useDocumentStore((s) => s.upload);
  const index = useDocumentStore((s) => s.index);
  const uploading = useDocumentStore((s) => s.uploading);
  const selectedExperimentRefs = useExperimentStore((s) => s.selectedRefs);
  const experimentDatasets = useExperimentStore((s) => s.datasets);
  const experimentGroupId = useExperimentStore((s) => s.groupChatId);
  const versionsByDataset = useExperimentStore((s) => s.versionsByDataset);
  const setExperimentGroup = useExperimentStore((s) => s.setGroup);
  const reconcileExperimentSelection = useExperimentStore((s) => s.reconcileSelection);
  const loadExperimentDatasets = useExperimentStore((s) => s.loadDatasets);
  const loadExperimentVersionDetails = useExperimentStore((s) => s.loadVersionDetails);

  const [serverRecord, setServerRecord] = useState<GroupChatRecord | null>(null);
  const [recordLoading, setRecordLoading] = useState(true);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [restoredMessageIds, setRestoredMessageIds] = useState<string[]>([]);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [activeDrawer, setActiveDrawer] = useState<DrawerKind>(null);
  const [pendingClarification, setPendingClarification] = useState<PendingClarification | null>(null);
  const [startingClarificationId, setStartingClarificationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendNotice, setSendNotice] = useState<string | null>(null);
  const historyLoadedGroups = useRef(new Set<string>());

  const record = serverRecord?.id === params.id ? serverRecord : null;

  const timelineMembers: TimelineMember[] = useMemo(
    () =>
      (record?.members ?? []).map((member) => ({
        id: member.id,
        display_name: member.displayName,
        role: member.role,
        agent_id: member.agentProfileRef?.object_id?.replace(/^agent:/, "") ?? undefined,
      })),
    [record],
  );

  const timeline: ChatTimelineItem[] = useMemo(
    () => {
      const persisted = messages.map((message) => {
        const item = toTimelineItem(message, timelineMembers);
        if (item.kind !== "clarification_ready" || !Array.isArray(item.payload.dataset_refs)) return item;
        const datasetLabels = item.payload.dataset_refs
          .map((value) => {
            if (typeof value !== "object" || value === null) return null;
            const ref = value as { dataset_id?: unknown; version?: unknown };
            if (typeof ref.dataset_id !== "string" || typeof ref.version !== "number") return null;
            const dataset = experimentDatasets.find((candidate) => candidate.dataset_id === ref.dataset_id);
             const version = versionsByDataset[ref.dataset_id]?.find((item) => item.version === ref.version);
             if (version) return `${version.filename} · v${version.version}`;
             return dataset && dataset.latest_version === ref.version
               ? `${dataset.filename} · v${ref.version}`
               : `实验数据版本 v${ref.version}`;
          })
          .filter((label): label is string => label !== null);
        return { ...item, payload: { ...item.payload, dataset_labels: datasetLabels } };
      });
      const liveProgress = activeRunGroupChatId === record?.id
        ? runtimeEvents.flatMap((event) => {
            const item = toChatRunEvent(event);
            return item !== null && item.kind !== "candidate" ? [item] : [];
          })
        : [];
      return [...persisted, ...liveProgress];
    },
    [activeRunGroupChatId, experimentDatasets, messages, record?.id, runtimeEvents, timelineMembers, versionsByDataset],
  );

  const loadMessages = useCallback(async (groupChatId: string): Promise<ChatMessageRecord[] | null> => {
    try {
      const items = await listGroupChatMessages(groupChatId);
      setMessages(items);
      if (!historyLoadedGroups.current.has(groupChatId)) {
        historyLoadedGroups.current.add(groupChatId);
        setRestoredMessageIds(items.map((item) => item.id));
      }
      setMessagesError(null);
      return items;
    } catch (err) {
      setMessagesError(readableError(err));
      return null;
    }
  }, []);

  const loadPendingClarification = useCallback(async (groupChatId: string): Promise<PendingClarification | null> => {
    try {
      const clarifications = await listTaskClarifications(groupChatId);
      const latest = clarifications.at(-1);
      reconcileExperimentSelection(latest?.dataset_refs ?? []);
      const next = pendingClarificationFromHistory(clarifications);
      setPendingClarification(next);
      return next;
    } catch {
      return null;
    }
  }, [reconcileExperimentSelection]);

  useEffect(() => {
    setExperimentGroup(params.id);
  }, [params.id, setExperimentGroup]);

  useEffect(() => {
    if (experimentGroupId !== params.id) return;
    void loadExperimentDatasets();
  }, [experimentGroupId, loadExperimentDatasets, params.id]);

  const timelineDatasetIds = useMemo(() => {
    const ids = new Set<string>();
    for (const message of messages) {
      if (message.kind !== "clarification_ready" || !Array.isArray(message.payload?.dataset_refs)) continue;
      for (const value of message.payload.dataset_refs) {
        if (typeof value === "object" && value !== null && typeof (value as { dataset_id?: unknown }).dataset_id === "string") {
          ids.add((value as { dataset_id: string }).dataset_id);
        }
      }
    }
    return [...ids];
  }, [messages]);

  useEffect(() => {
    if (experimentGroupId !== params.id || timelineDatasetIds.length === 0) return;
    void Promise.all(timelineDatasetIds.map((datasetId) => loadExperimentVersionDetails(datasetId)));
  }, [experimentGroupId, loadExperimentVersionDetails, params.id, timelineDatasetIds]);

  useEffect(() => {
    hydrate();
    void (async () => {
      setRecordLoading(true);
      setRecordError(null);
      setServerRecord(null);
      try {
        const response = await getGroupChat(params.id);
        const nextRecord = recordFromResponse(response);
        const existingSchedule =
          useGroupChatStore
            .getState()
            .records.find((item) => item.id === nextRecord.id)?.meetingSchedule ?? null;
        upsertRecord(nextRecord);
        setServerRecord({ ...nextRecord, meetingSchedule: existingSchedule });
        await loadMessages(nextRecord.id);
        await loadPendingClarification(nextRecord.id);
      } catch (err) {
        setServerRecord(null);
        setRecordError(readableError(err));
      } finally {
        setRecordLoading(false);
      }
    })();
  }, [params.id, hydrate, upsertRecord, loadMessages, loadPendingClarification]);

  useEffect(() => {
    if (record?.id === undefined) return;
    void getMeetingSchedule(record.id)
      .then((schedule) => {
        const next =
          schedule === null
            ? null
            : {
                nextMeetingAt: dateTimeInputValue(schedule.next_meeting_at),
                updatedAt: schedule.updated_at * 1000,
              };
        updateMeetingSchedule(record.id, next);
        setServerRecord((current) => (current ? { ...current, meetingSchedule: next } : current));
      })
      .catch(() => {
        // The group remains usable; the next save reports the server error.
      });
  }, [record?.id, updateMeetingSchedule]);

  useEffect(() => () => useRunStore.getState().stop(), []);

  useEffect(() => {
    if (!record?.id) return;
    void resumeRun(record.id);
  }, [record?.id, resumeRun]);

  useEffect(() => {
    if (!record?.id || activeRunGroupChatId !== record.id || !activeRunId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const refreshRunMessages = async () => {
      const next = await loadMessages(record.id);
      if (cancelled || next === null) return;
      const hasTerminalProjection = next.some((message) => {
        const runId = message.payload?.run_id;
        const status = message.payload?.status;
        return runId === activeRunId && typeof status === "string" && TERMINAL_RUN_STATUSES.has(status);
      });
      if (!hasTerminalProjection) {
        timer = setTimeout(() => void refreshRunMessages(), 1000);
      }
    };

    void refreshRunMessages();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [record?.id, activeRunGroupChatId, activeRunId, activeRunStatus, loadMessages]);

  useEffect(() => {
    if (activeDrawer === null) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActiveDrawer(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [activeDrawer]);

  if (!hydrated) {
    return (
      <div className="mx-auto max-w-3xl p-8 text-sm text-muted-foreground">
        正在恢复课题组记录…
      </div>
    );
  }

  if (recordLoading) {
    return (
      <div className="mx-auto max-w-3xl p-8 text-sm text-muted-foreground">
        正在读取服务端课题组详情…
      </div>
    );
  }

  if (recordError !== null) {
    return (
      <div className="mx-auto max-w-3xl p-8 text-sm text-destructive">
        课题组读取失败：{recordError}
        <div className="mt-3 flex gap-2">
          <Button onClick={() => void loadMessages(params.id)}>重试</Button>
          <Button variant="outline" onClick={() => router.push("/")}>
            返回课题组
          </Button>
        </div>
      </div>
    );
  }

  if (!record) {
    return (
      <div className="mx-auto max-w-3xl p-8 text-sm text-muted-foreground">
        服务端没有找到这条课题组记录。
        <div className="mt-3">
          <Button
            variant="destructive"
            onClick={() => {
              removeCachedGroupChat(params.id);
              useRunStore.getState().reset();
              router.push("/");
            }}
          >
            移除本地记录
          </Button>
        </div>
      </div>
    );
  }

  const handleComposerSubmit = async (draft: ComposerDraft) => {
    setSending(true);
    setSendNotice(null);
    try {
      const result = await submitLiveChatDraft({
        groupChatId: record.id,
        draft,
        pendingClarification,
        api: {
          saveMessage: (request) => createGroupChatMessage(record.id, request),
          createClarification: (request) => createTaskClarification(record.id, request),
          answerClarification: (clarificationId, request) =>
            answerTaskClarification(record.id, clarificationId, request),
        },
        selectedDatasetRefs: selectedExperimentRefs,
      });
      setPendingClarification(result.pendingClarification);
      if (result.readyToStart) setSendNotice("澄清已完成，可以开始分析。");
      await loadMessages(record.id);
    } catch (err) {
      setSendNotice(`操作失败：${readableError(err)}`);
      await Promise.all([loadMessages(record.id), loadPendingClarification(record.id)]);
    } finally {
      setSending(false);
    }
  };

  const handleStartLive = async (clarificationId: string) => {
    if (startingClarificationId !== null) return;
    setStartingClarificationId(clarificationId);
    setSendNotice(null);
    try {
      await startClarificationLive(record.id, clarificationId);
      setPendingClarification(null);
      await loadMessages(record.id);
    } catch (err) {
      setSendNotice(`启动分析失败：${readableError(err)}`);
    } finally {
      setStartingClarificationId(null);
    }
  };

  const handleScheduleMeeting = async (nextMeetingAt: string) => {
    try {
      const saved = await saveMeetingSchedule(record.id, nextMeetingAt);
      const next = {
        nextMeetingAt: dateTimeInputValue(saved.next_meeting_at),
        updatedAt: saved.updated_at * 1000,
      };
      updateMeetingSchedule(record.id, next);
      setServerRecord((current) => (current ? { ...current, meetingSchedule: next } : current));
      setSendNotice(`下次组会已置顶：${next.nextMeetingAt.replace("T", " ")}`);
      await loadMessages(record.id);
    } catch (err) {
      setSendNotice(`组会时间保存失败：${readableError(err)}`);
    }
  };

  const handleFileSelected = async (file: File) => {
    setSendNotice(null);
    try {
      const document = await upload(record.id, file);
      if (document) await index(record.id, document.document_id);
      await loadMessages(record.id);
    } catch (err) {
      setSendNotice(`上传失败：${readableError(err)}`);
    }
  };

  const handleConfigureMember = async (memberId: string, configuration: import("@/lib/api").GenerateProfile) => {
    const response = await configureGeneratedMember(record.id, memberId, configuration);
    const nextRecord = {
      ...recordFromResponse(response),
      meetingSchedule: record.meetingSchedule,
    };
    upsertRecord(nextRecord);
    setServerRecord(nextRecord);
  };

  const toggleDrawer = (kind: Exclude<DrawerKind, null>) => {
    setActiveDrawer((current) => (current === kind ? null : kind));
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex min-h-14 flex-row items-center gap-2 overflow-x-auto border-b px-3 py-2 sm:px-4">
        <div className="min-w-0 flex-1 sm:w-auto sm:max-w-xl">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">{record.topicName}</h1>
            <Badge variant="secondary" className="shrink-0 whitespace-nowrap">{record.members.length} 名成员</Badge>
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{record.topicSummary}</p>
        </div>
        {record.meetingSchedule !== null && (
          <div className="ml-2 hidden items-center gap-1 rounded border border-primary/30 bg-primary/5 px-2 py-1 text-xs sm:flex">
            <CalendarDays className="size-3.5 text-primary" aria-hidden />
            <span className="text-primary">下次组会：{record.meetingSchedule.nextMeetingAt.replace("T", " ")}</span>
          </div>
        )}
        <div className="flex shrink-0 items-center justify-end gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={() => toggleDrawer("members")}
            aria-label="成员"
          >
            <UsersRound className="size-4" />
            <span className="hidden sm:inline">成员</span>
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => toggleDrawer("artifacts")}
            aria-label="查看产物"
          >
            <FileText className="size-4" />
            <span className="hidden sm:inline">产物</span>
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => toggleDrawer("experiments")}
            aria-label="实验数据"
          >
            <FlaskConical className="size-4" />
            <span className="hidden sm:inline">实验数据</span>
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => toggleDrawer("search")}
            aria-label="搜索聊天记录"
          >
            <Search className="size-4" />
            <span className="hidden sm:inline">聊天记录</span>
          </Button>
        </div>
      </header>

      {messagesError !== null && (
        <p className="px-4 pt-2 text-xs text-destructive">消息读取失败：{messagesError}</p>
      )}
      {sendNotice !== null && (
        <p className="px-4 pt-2 text-xs text-muted-foreground">{sendNotice}</p>
      )}

        <ChatTranscript
        groupChatId={record.id}
        items={timeline}
        restoredMessageIds={restoredMessageIds}
          onStartLive={(clarificationId) => void handleStartLive(clarificationId)}
          startingClarificationId={startingClarificationId}
        onScheduleMeeting={(nextMeetingAt) => void handleScheduleMeeting(nextMeetingAt)}
        onOpenArtifact={() => setActiveDrawer("artifacts")}
      />

      <ChatComposer
        targets={mentionTargetsForActiveMembers(record.members)}
        onSubmit={(draft) => void handleComposerSubmit(draft)}
        onFileSelected={(file) => void handleFileSelected(file)}
        uploading={uploading}
        sending={sending}
        selectedDatasetSummary={selectedDatasetSummary(experimentDatasets, selectedExperimentRefs)}
        onOpenExperiments={() => setActiveDrawer("experiments")}
      />

      {activeDrawer !== null && (
        <div className="fixed inset-0 z-50 flex" role="presentation">
          <div
            className="absolute inset-0 bg-black/30"
            role="presentation"
            onClick={() => setActiveDrawer(null)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={activeDrawer === "artifacts" ? "产物" : activeDrawer === "members" ? "成员" : activeDrawer === "experiments" ? "实验数据" : "聊天记录"}
            className="relative ml-auto flex h-full w-full flex-col overflow-y-auto border-l bg-background p-3 sm:w-[min(26rem,calc(100vw-2rem))]"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-sm font-medium">
                {activeDrawer === "artifacts" ? "产物" : activeDrawer === "members" ? "成员" : activeDrawer === "experiments" ? "实验数据" : "聊天记录"}
              </p>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => setActiveDrawer(null)}
                title="关闭"
                aria-label="关闭"
              >
                <X className="size-4" />
              </Button>
            </div>
            {activeDrawer === "experiments" ? (
              <ExperimentWorkspacePanel groupChatId={record.id} />
            ) : activeDrawer === "artifacts" ? (
              <ArtifactPanel members={record.members} artifacts={artifacts} />
            ) : activeDrawer === "members" ? (
              <MemberPanel members={record.members} onConfigure={handleConfigureMember} />
            ) : (
              <ChatSearchPanel
                groupChatId={record.id}
                members={record.members}
                onClose={() => setActiveDrawer(null)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
