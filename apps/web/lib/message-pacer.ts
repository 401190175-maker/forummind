/**
 * 确定性回复节奏器（design §4.5）。
 *
 * 只负责呈现时序：打字指示在 250ms 出现，首段正文不早于 900ms，
 * 相邻状态消息至少间隔 700ms，正文以每分钟 45–65 个汉字的速度展开。
 * 后端工作与 SSE 摄入绝不被本模块延迟——它只是把已经到达的消息按
 * 一个确定的时间轴“播放”出来。
 */

export const TYPING_DELAY_MS = 250;
export const FIRST_TEXT_DELAY_MS = 900;
export const STATUS_GAP_MS = 700;
export const MIN_CHARS_PER_SECOND = 45;
export const MAX_CHARS_PER_SECOND = 65;

/** 错误/取消类呈现的硬上限：远端失败最迟在 500ms 内可见。 */
export const MAX_ERROR_DELAY_MS = 500;

const DEFAULT_CHARS_PER_SECOND = (MIN_CHARS_PER_SECOND + MAX_CHARS_PER_SECOND) / 2;

/** 注入时钟，便于单元测试用假时钟驱动。 */
export interface Clock {
  now(): number;
}

/** 待播放的 Agent 消息（SSE 摄入后交给 pacer 的元数据）。 */
export interface PaceableAgentMessage {
  id: string;
  replyToId: string | null;
  receivedAt: number;
  sentAt: number;
  content: string;
  kind?: string;
  /** 本地校验/取消等需要立即显示的消息，跳过打字与首段延迟。 */
  priority?: "immediate";
}

/** 某一时刻呈现出的单条消息状态。 */
export interface PacedMessage {
  id: string;
  typing: boolean;
  visibleText: string;
}

interface PacingEntry {
  message: PaceableAgentMessage;
  enqueuedAt: number;
  restored: boolean;
  shownAt: number | null;
  doneAt: number | null;
}

export class MessagePacer {
  private entries: PacingEntry[] = [];

  constructor(private readonly clock: Clock) {}

  enqueue(message: PaceableAgentMessage): void {
    this.entries.push({
      message,
      enqueuedAt: this.clock.now(),
      restored: false,
      shownAt: null,
      doneAt: null,
    });
  }

  cancel(messageId: string): void {
    this.entries = this.entries.filter((entry) => entry.message.id !== messageId);
  }

  restore(messageIds: string[]): void {
    const ids = new Set(messageIds);
    const now = this.clock.now();
    for (const entry of this.entries) {
      if (ids.has(entry.message.id)) {
        entry.restored = true;
        entry.shownAt = now;
        entry.doneAt = now;
      }
    }
  }

  snapshot(now?: number): PacedMessage[] {
    const current = now ?? this.clock.now();
    const result: PacedMessage[] = [];
    let prevDoneAt = Number.NEGATIVE_INFINITY;

    for (const entry of this.entries) {
      if (entry.restored) {
        result.push({
          id: entry.message.id,
          typing: false,
          visibleText: entry.message.content,
        });
        prevDoneAt = Math.max(prevDoneAt, entry.doneAt ?? current);
        continue;
      }

      const { startAt, textStartAt, doneAt } = this.timeline(entry, prevDoneAt);
      let typing = false;
      let visibleText = "";

      if (current >= startAt) {
        typing = current < doneAt;
        if (current >= textStartAt) {
          const elapsedMs = current - textStartAt;
          const charCount = Math.floor(
            (elapsedMs / 1000) * DEFAULT_CHARS_PER_SECOND,
          ) + 1;
          visibleText = entry.message.content.slice(0, charCount);
          if (current >= doneAt) {
            visibleText = entry.message.content;
          }
        }
      }

      result.push({ id: entry.message.id, typing, visibleText });
      prevDoneAt = Math.max(prevDoneAt, doneAt);
    }

    return result;
  }

  private timeline(
    entry: PacingEntry,
    prevDoneAt: number,
  ): { startAt: number; textStartAt: number; doneAt: number } {
    const immediate = entry.message.priority === "immediate";
    const typingDelay = immediate ? 0 : TYPING_DELAY_MS;
    const firstTextDelay = immediate ? 0 : FIRST_TEXT_DELAY_MS;
    const startAt = Math.max(entry.enqueuedAt + typingDelay, prevDoneAt + STATUS_GAP_MS);
    const textStartAt = startAt + (firstTextDelay - typingDelay);
    const textDurationMs =
      (entry.message.content.length / DEFAULT_CHARS_PER_SECOND) * 1000;
    const doneAt = textStartAt + textDurationMs;
    return { startAt, textStartAt, doneAt };
  }
}
