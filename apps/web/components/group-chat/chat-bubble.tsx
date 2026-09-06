"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { ChatSide } from "./chat-types";

type Props = {
  side: ChatSide;
  senderName?: string;
  children: ReactNode;
};

/**
 * 微信风格气泡：左侧 Agent、右侧用户，稳定最大宽度与圆角，
 * 长文件名自动换行，发送者标签只出现在左侧 Agent 消息上。
 */
export function ChatBubble({ side, senderName, children }: Props) {
  return (
    <div className={cn("flex w-full", side === "right" ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[min(26rem,calc(100vw-2rem))] break-words rounded-[7px] px-3 py-2 text-sm",
          side === "right"
            ? "bg-primary/10 text-foreground"
            : "border bg-card text-foreground",
        )}
      >
        {side === "left" && senderName ? (
          <p className="mb-1 text-xs font-medium text-muted-foreground">{senderName}</p>
        ) : null}
        {children}
      </div>
    </div>
  );
}
