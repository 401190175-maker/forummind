"use client";

import { useRef, useState } from "react";

import { FlaskConical, Paperclip, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MentionPicker } from "./mention-picker";
import type { ComposerDraft, MentionTarget } from "./types";

type Props = {
  /** 可 `@` 对象列表（全体、角色、成员）。 */
  targets: MentionTarget[];
  /** 提交草稿（父组件决定后续动作；不绑定 startRun）。 */
  onSubmit?: (draft: ComposerDraft) => void;
  /** 用户从隐藏文件输入选择文件时通知父组件（触发真实上传）。 */
  onFileSelected?: (file: File) => void;
  /** 点击聊天记录搜索入口时通知父组件。 */
  onSearchClick?: () => void;
  /** 搜索面板当前是否打开（用于高亮入口）。 */
  searchActive?: boolean;
  /** 提交进行中（发送按钮禁用并显示“发送中…”，防止重复提交）。 */
  sending?: boolean;
  /** 文件上传进行中。 */
  uploading?: boolean;
  /** 当前明确选择的数据集版本摘要。 */
  selectedDatasetSummary?: { count: number; labels: string[] };
  /** 打开实验数据抽屉。 */
  onOpenExperiments?: () => void;
  /** 输入区占位文案。 */
  placeholder?: string;
};

/**
 * 底部群聊输入工具区（design.md §2.1，tasks.md Task 3）。
 *
 * 提供 `@`、文件、聊天记录搜索、发送四个可见入口：
 * - `@`：打开 `MentionPicker`；输入 `@` 也会打开。
 * - 文件：只显示 demo 未接入提示，不触发真实上传。
 * - 对话气泡：通过回调通知父组件打开搜索面板。
 * - 发送：空文本禁用；提交只产生 `ComposerDraft`，不启动 run。
 */
export function ChatComposer({
  targets,
  onSubmit,
  onFileSelected,
  onSearchClick,
  searchActive = false,
  sending = false,
  uploading = false,
  selectedDatasetSummary,
  onOpenExperiments,
  placeholder = "输入消息，@ 可点名成员、角色或全体…",
}: Props) {
  const [text, setText] = useState("");
  const [mention, setMention] = useState<MentionTarget | null>(null);
  const [mentionRange, setMentionRange] = useState<{ start: number; end: number } | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [caret, setCaret] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canSend = text.trim().length > 0 && !sending;

  const handleTextChange = (value: string, caret: number) => {
    setCaret(caret);
    setText(value);
    if (mention !== null && mentionRange !== null) {
      const token = `@${mention.label}`;
      if (value.slice(mentionRange.start, mentionRange.end) !== token) {
        setMention(null);
        setMentionRange(null);
      }
    }
    const trigger = value.lastIndexOf("@", Math.max(caret - 1, 0));
    const canStartMention = trigger >= 0 && (trigger === 0 || /\s/.test(value[trigger - 1]));
    if (canStartMention && mention === null) {
      setMentionRange({ start: trigger, end: trigger + 1 });
      setPickerOpen(true);
    } else if (!canStartMention && mention === null) {
      setPickerOpen(false);
    }
  };

  const handleSelect = (target: MentionTarget) => {
    const range = mentionRange ?? {
      start: caret,
      end: caret,
    };
    const replacement = `@${target.label}`;
    const nextText = `${text.slice(0, range.start)}${replacement}${text.slice(range.end)}`;
    setText(nextText);
    setMention(target);
    setMentionRange({ start: range.start, end: range.start + replacement.length });
    setPickerOpen(false);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(
        range.start + replacement.length,
        range.start + replacement.length,
      );
    });
  };

  const handleMentionButtonClick = () => {
    if (mention !== null) {
      setPickerOpen((value) => !value);
      return;
    }
    const nextText = `${text.slice(0, caret)}@${text.slice(caret)}`;
    setText(nextText);
    setMentionRange({ start: caret, end: caret + 1 });
    setPickerOpen(true);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(caret + 1, caret + 1);
    });
  };

  const handleCancelMention = () => {
    if (mentionRange !== null) {
      setText(`${text.slice(0, mentionRange.start)}${text.slice(mentionRange.end)}`);
    }
    setMention(null);
    setMentionRange(null);
    setCaret((value) => Math.max(0, value - 1));
  };

  const handleFileClick = () => {
    fileInputRef.current?.click();
  };

  const handleSend = () => {
    if (!canSend) return;
    const draft: ComposerDraft = { text: text.trim(), mention };
    onSubmit?.(draft);
    setText("");
    setMention(null);
    setMentionRange(null);
    setCaret(0);
    setPickerOpen(false);
  };

  return (
    <div className="border-t bg-card">
      <div className="mx-auto w-full max-w-5xl p-3">
        {/* 已选 `@` 对象 + 文件提示 */}
        <div className="mb-1.5 flex min-h-5 items-center gap-2">
          {mention !== null && (
            <span className="inline-flex items-center rounded border bg-muted/40 px-2 py-0.5 text-xs">
              <span className="text-primary">@</span>
              <span className="ml-1 font-medium">{mention.label}</span>
              <button
                type="button"
                aria-label="取消点名"
                onClick={handleCancelMention}
                className="ml-1.5 text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </span>
          )}
          {selectedDatasetSummary && selectedDatasetSummary.count > 0 && (
            <button type="button" onClick={onOpenExperiments} className="inline-flex min-w-0 items-center gap-1.5 rounded border border-primary/25 bg-primary/5 px-2 py-0.5 text-[11px] text-primary hover:bg-primary/10" title="打开实验数据工作区">
              <FlaskConical className="size-3" aria-hidden />
              <span className="truncate">已选 {selectedDatasetSummary.labels.join("、")}</span>
            </button>
          )}
          {mention !== null && (
            <span className="text-[11px] text-muted-foreground">
              带 @ 提交将进入苏格拉底式任务澄清（先提问，不直接执行）
            </span>
          )}
        </div>

        {/* 输入框 + `@` 浮层 */}
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => handleTextChange(e.target.value, e.target.selectionStart)}
            onSelect={(e) => {
              const target = e.currentTarget;
              setCaret(target.selectionStart);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={placeholder}
            rows={2}
            className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
          <div className="absolute bottom-full left-0 z-10 mb-1">
            <MentionPicker
              targets={targets}
              open={pickerOpen}
              onSelect={handleSelect}
            />
          </div>
        </div>

        {/* 底部工具区：@ / 文件 / 搜索 / 发送 */}
        <div className="mt-2 flex items-center gap-1">
          <button
            type="button"
            onClick={handleMentionButtonClick}
            className={cn(
              "rounded px-2.5 py-1 text-sm transition-colors hover:bg-secondary/60",
              pickerOpen && "bg-secondary text-secondary-foreground",
            )}
          >
            @
          </button>
          <button
            type="button"
            onClick={onOpenExperiments}
            className="inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
            title="实验数据"
          >
            <FlaskConical className="size-3.5" aria-hidden />实验数据
          </button>
          <button
            type="button"
            onClick={handleFileClick}
            disabled={uploading}
            aria-label="上传资料"
            className="rounded px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground disabled:opacity-50"
          >
            <Paperclip className="inline h-3.5 w-3.5" aria-hidden />{" "}
            {uploading ? "上传中…" : "文件"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.markdown"
            aria-label="上传资料"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onFileSelected?.(file);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={onSearchClick}
            className={cn(
              "rounded px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground",
              searchActive && "bg-secondary text-secondary-foreground",
            )}
            title="搜索聊天记录"
          >
               <Search className="inline h-3.5 w-3.5" aria-hidden /> 聊天记录
          </button>
          <div className="flex-1" />
          <Button size="sm" disabled={!canSend} onClick={handleSend}>
            {sending ? "发送中…" : "发送"}
          </Button>
        </div>
      </div>
    </div>
  );
}
