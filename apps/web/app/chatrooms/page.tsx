"use client";

import { useState } from "react";

import { DiscussionDetail } from "@/components/discussion/discussion-detail";
import { DiscussionList } from "@/components/discussion/discussion-list";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StructuredChain } from "@/components/discussion/structured-chain";
import { demoDiscussions } from "@/lib/demo-discussions";

type ViewMode = "discussion" | "summary" | "chain" | "markdown";

const VIEW_MODES: Array<{ value: ViewMode; label: string }> = [
  { value: "discussion", label: "完整讨论" },
  { value: "summary", label: "AI 纪要" },
  { value: "chain", label: "结构化链路" },
  { value: "markdown", label: "Markdown 预览" },
];

export default function ChatroomsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(demoDiscussions[0]?.id ?? null);
  const [viewMode, setViewMode] = useState<ViewMode>("discussion");
  const selectedDiscussion =
    demoDiscussions.find((discussion) => discussion.id === selectedId) ?? demoDiscussions[0] ?? null;

  return (
    <div className="mx-auto max-w-6xl p-6 sm:p-8">
      <header className="border-b pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">聊天室</h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              查看 Agent 非组会状态下的自由讨论记录、AI 纪要和可审阅的讨论链路。
            </p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Badge variant="outline">自由讨论记录库</Badge>
            <Badge variant="secondary">synthetic demo</Badge>
          </div>
        </div>
        <p className="mt-4 text-xs leading-5 text-muted-foreground">
          聊天室不是课题组实时群聊，也不是正式组会；当前记录未持久化，不会改变 Run、Memory 或 ResearchState。
        </p>
      </header>

      <main className="mt-6 grid gap-6 lg:grid-cols-[minmax(220px,0.34fr)_minmax(0,1fr)]">
        <section className="min-w-0" aria-labelledby="discussion-list-heading">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <h2 id="discussion-list-heading" className="text-base font-semibold">
                自由讨论记录
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">按课题和记录时间浏览 demo 内容</p>
            </div>
            <Badge variant="outline">{demoDiscussions.length} 条</Badge>
          </div>
          <DiscussionList
            discussions={demoDiscussions}
            selectedId={selectedDiscussion?.id ?? null}
            onSelect={setSelectedId}
          />
        </section>

        <section className="min-w-0" aria-labelledby="discussion-detail-heading">
          {selectedDiscussion ? (
            <div className="space-y-4" id="discussion-detail-heading">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">当前记录</p>
                  <h2 className="break-words text-base font-semibold">{selectedDiscussion.title}</h2>
                </div>
                <div className="flex max-w-full flex-wrap gap-1.5" role="tablist" aria-label="讨论记录视图">
                  {VIEW_MODES.map((mode) => (
                    <Button
                      key={mode.value}
                      type="button"
                      size="sm"
                      variant={viewMode === mode.value ? "secondary" : "outline"}
                      role="tab"
                      aria-selected={viewMode === mode.value}
                      onClick={() => setViewMode(mode.value)}
                    >
                      {mode.label}
                    </Button>
                  ))}
                </div>
              </div>

              {viewMode === "discussion" && <DiscussionDetail discussion={selectedDiscussion} />}

              {viewMode === "summary" && (
                <section className="space-y-5 rounded-md border bg-card p-5">
                  <div className="space-y-2 border-b pb-4">
                    <h3 className="text-lg font-semibold">AI 纪要</h3>
                    <p className="text-sm leading-6 text-muted-foreground">
                      {selectedDiscussion.summary.overview}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">synthetic</Badge>
                      <Badge variant="secondary">not_persisted</Badge>
                    </div>
                  </div>
                  <div className="grid gap-5 lg:grid-cols-2">
                    <div>
                      <h4 className="text-sm font-semibold">关键观点</h4>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6">
                        {selectedDiscussion.summary.keyPoints.map((point) => (
                          <li key={point}>{point}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold">未决分歧</h4>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-muted-foreground">
                        {selectedDiscussion.summary.unresolvedDisagreements.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <div className="space-y-2 border-t pt-4">
                    <h4 className="text-sm font-semibold">当前结论</h4>
                    <p className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm leading-6">
                      {selectedDiscussion.summary.currentConclusion}
                    </p>
                    <h4 className="pt-2 text-sm font-semibold">下一步建议</h4>
                    <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-muted-foreground">
                      {selectedDiscussion.summary.actionItems.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                </section>
              )}

              {viewMode === "chain" && (
                <section className="rounded-md border bg-card p-5">
                  <StructuredChain turns={selectedDiscussion.turns} />
                </section>
              )}

              {viewMode === "markdown" && <MarkdownPreview document={selectedDiscussion.markdown} />}
            </div>
          ) : (
            <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
              当前没有可查看的自由讨论记录。
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
