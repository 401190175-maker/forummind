import { Badge } from "@/components/ui/badge";
import type { DemoDiscussionRecord } from "@/lib/demo-discussions";
import { cn } from "@/lib/utils";

type Props = {
  discussions: DemoDiscussionRecord[];
  selectedId: string | null;
  onSelect: (discussionId: string) => void;
};

function statusLabel(status: DemoDiscussionRecord["status"]): string {
  return status === "completed" ? "已收束" : "待补证";
}

export function DiscussionList({ discussions, selectedId, onSelect }: Props) {
  if (discussions.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        当前没有可查看的自由讨论记录。
      </div>
    );
  }

  return (
    <div className="space-y-2" role="listbox" aria-label="自由讨论记录">
      {discussions.map((discussion) => {
        const selected = discussion.id === selectedId;
        return (
          <button
            key={discussion.id}
            type="button"
            role="option"
            aria-selected={selected}
            onClick={() => onSelect(discussion.id)}
            className={cn(
              "w-full rounded-md border p-3 text-left transition-colors",
              "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              selected
                ? "border-primary/60 bg-primary/10"
                : "bg-card hover:border-primary/40 hover:bg-accent/60",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <span className="min-w-0 break-words text-sm font-medium">{discussion.title}</span>
              <Badge variant={discussion.status === "completed" ? "success" : "warning"}>
                {statusLabel(discussion.status)}
              </Badge>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{discussion.topic}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {discussion.participants.map((participant) => participant.name).join(" / ")}
            </p>
            <p className="mt-2 text-[11px] text-muted-foreground">
              {discussion.startedAt} - {discussion.endedAt}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge variant="outline">自由讨论</Badge>
              <Badge variant="secondary">synthetic</Badge>
            </div>
          </button>
        );
      })}
    </div>
  );
}
