"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { FolderOpen } from "lucide-react";

import { CandidateReview } from "@/components/research/candidate-review";
import { MessagePacer } from "@/lib/message-pacer";
import { ChatAttachment } from "./chat-attachment";
import { ChatBubble } from "./chat-bubble";
import { MeetingScheduleMessage } from "./meeting-schedule-message";
import { TaskReadyMessage } from "./task-ready-message";
import type { ChatTimelineItem } from "./chat-types";

type Props = {
  groupChatId: string;
  items: ChatTimelineItem[];
  restoredMessageIds?: string[];
  onStartLive?: (clarificationId: string) => void;
  startingClarificationId?: string | null;
  onScheduleMeeting?: (nextMeetingAt: string) => void;
  onOpenArtifact?: () => void;
};

/**
 * 单一可滚动的语义消息列表。未知 kind 一律回退为纯文本气泡，
 * 会议安排与“开始分析”命令都渲染在它们所属的气泡内部。
 */
export function ChatTranscript({
  groupChatId,
  items,
  restoredMessageIds = [],
  onStartLive,
  startingClarificationId = null,
  onScheduleMeeting,
  onOpenArtifact,
}: Props) {
  const transcriptRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  const stickToBottomRef = useRef(true);
  const programmaticScrollTopRef = useRef<number | null>(null);
  const pacingRef = useRef<{
    groupChatId: string;
    pacer: MessagePacer;
    knownItemIds: Set<string>;
    restoredItemIds: Set<string>;
    contentById: Map<string, string>;
  } | null>(null);
  const [pacingRevision, setPacingRevision] = useState(0);
  const latestMessageId = items.at(-1)?.id;

  useLayoutEffect(() => {
    if (pacingRef.current?.groupChatId !== groupChatId) {
      pacingRef.current = {
        groupChatId,
        pacer: new MessagePacer({ now: () => Date.now() }),
        knownItemIds: new Set(),
        restoredItemIds: new Set(),
        contentById: new Map(),
      };
    }
    const playback = pacingRef.current;
    const restoredIds = new Set(restoredMessageIds);
    for (const item of items) {
      if (!isPaceable(item) || playback.knownItemIds.has(item.id)) continue;
      playback.knownItemIds.add(item.id);
      playback.contentById.set(item.id, item.content);
      playback.pacer.enqueue({
        id: item.id,
        replyToId: null,
        receivedAt: item.createdAt,
        sentAt: item.createdAt,
        content: item.content,
        kind: item.kind,
      });
    }
    for (const itemId of restoredIds) {
      if (playback.knownItemIds.has(itemId) && !playback.restoredItemIds.has(itemId)) {
        playback.pacer.restore([itemId]);
        playback.restoredItemIds.add(itemId);
      }
    }

    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = () => {
      const states = playback.pacer.snapshot();
      setPacingRevision((revision) => revision + 1);
      const hasPendingPlayback = states.some((state) => {
        const fullText = playback.contentById.get(state.id);
        return fullText !== undefined && (state.typing || state.visibleText !== fullText);
      });
      if (hasPendingPlayback) timer = setTimeout(tick, 50);
    };
    tick();
    return () => {
      if (timer !== null) clearTimeout(timer);
    };
  }, [groupChatId, items, restoredMessageIds]);

  const renderedItems = useMemo(() => {
    const playback = pacingRef.current;
    if (playback?.groupChatId !== groupChatId) return items;
    const states = new Map(playback.pacer.snapshot().map((state) => [state.id, state]));
    return items.map((item) => {
      const state = states.get(item.id);
      return state === undefined ? item : { ...item, content: state.visibleText, typing: state.typing };
    });
  }, [groupChatId, items, pacingRevision]);

  useLayoutEffect(() => {
    const transcript = transcriptRef.current;
    const content = contentRef.current;
    if (transcript === null || content === null) return;

    initializedRef.current = false;
    stickToBottomRef.current = true;
    const updateStickiness = () => {
      const expectedScrollTop = programmaticScrollTopRef.current;
      if (expectedScrollTop !== null && Math.abs(transcript.scrollTop - expectedScrollTop) < 1) {
        programmaticScrollTopRef.current = null;
        stickToBottomRef.current = true;
        return;
      }
      programmaticScrollTopRef.current = null;
      const distanceFromBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight;
      stickToBottomRef.current = distanceFromBottom < 96;
    };
    const scrollToBottom = () => {
      transcript.scrollTop = transcript.scrollHeight;
      programmaticScrollTopRef.current = transcript.scrollTop;
    };
    let frame: number | null = null;
    const keepBottomVisible = () => {
      if (!stickToBottomRef.current) return;
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        if (stickToBottomRef.current) scrollToBottom();
      });
    };
    const resizeObserver = new ResizeObserver(keepBottomVisible);
    resizeObserver.observe(content);
    const mutationObserver = new MutationObserver(keepBottomVisible);
    mutationObserver.observe(content, { childList: true, subtree: true, characterData: true });
    transcript.addEventListener("scroll", updateStickiness, { passive: true });
    keepBottomVisible();
    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
      transcript.removeEventListener("scroll", updateStickiness);
    };
  }, [groupChatId]);

  useLayoutEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript === null) return;
    if (!initializedRef.current || stickToBottomRef.current) {
      transcript.scrollTop = transcript.scrollHeight;
      programmaticScrollTopRef.current = transcript.scrollTop;
      stickToBottomRef.current = true;
    }
    initializedRef.current = true;
  }, [latestMessageId]);

  return (
    <div
      ref={transcriptRef}
      role="list"
      data-testid="research-chat"
      className="flex-1 overflow-y-auto px-3 py-4"
    >
      <div ref={contentRef} className="space-y-3">
        {renderedItems.map((item) => (
          <div key={item.id} role="listitem">
            <ChatBubble side={item.side} senderName={item.senderName}>
              {renderBody(item)}
            </ChatBubble>
          </div>
        ))}
      </div>
    </div>
  );

  function renderBody(item: ChatTimelineItem & { typing?: boolean }) {
    if (item.typing && item.content.length === 0) {
      return <p data-testid="chat-typing" aria-live="polite" className="text-xs text-muted-foreground">正在输入…</p>;
    }
    switch (item.kind) {
      case "attachment":
        return <ChatAttachment content={item.content} payload={item.payload} />;
      case "meeting_schedule":
        return (
          <MeetingScheduleMessage
            onSave={(nextMeetingAt) => onScheduleMeeting?.(nextMeetingAt)}
          />
        );
      case "clarification_ready":
        return (
          <TaskReadyMessage
            payload={item.payload}
            pending={startingClarificationId !== null}
            onStart={(clarificationId) => onStartLive?.(clarificationId)}
          />
        );
      case "candidate": {
        const runId = typeof item.payload.run_id === "string" ? item.payload.run_id : null;
        const runStatus = typeof item.payload.status === "string" ? item.payload.status : undefined;
        if (runId !== null) {
          return <CandidateReview groupChatId={groupChatId} runId={runId} runStatus={runStatus} variant="chat" />;
        }
        return (
          <div className="space-y-2">
            <p className="whitespace-pre-wrap">{item.content}</p>
            <button
              type="button"
              onClick={() => onOpenArtifact?.()}
              className="inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
            >
              <FolderOpen className="h-3.5 w-3.5" aria-hidden />
              查看产物
            </button>
          </div>
        );
      }
      default:
        return <p className="whitespace-pre-wrap">{item.content}</p>;
    }
  }
}

function isPaceable(item: ChatTimelineItem): boolean {
  return item.side === "left" && !["attachment", "candidate", "clarification_ready", "meeting_schedule"].includes(item.kind);
}
