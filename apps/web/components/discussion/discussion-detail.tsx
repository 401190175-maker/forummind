import { Badge } from "@/components/ui/badge";
import type {
  DemoDiscussionRecord,
  DiscussionTurn,
  LinkedObject,
} from "@/lib/demo-discussions";

type Props = {
  discussion: DemoDiscussionRecord;
};

const TURN_LABELS: Record<DiscussionTurn["kind"], string> = {
  question: "问题",
  viewpoint: "观点",
  evidence: "证据",
  challenge: "质疑",
  response: "回应",
  revision: "修订",
  conclusion: "结论",
};

const LINKED_OBJECT_LABELS: Record<LinkedObject["type"], string> = {
  task: "任务",
  evidence_gap: "证据缺口",
  claim: "Claim",
};

function certaintyLabel(certainty: DiscussionTurn["certainty"]): string {
  if (certainty === "supported") return "已有记录支持";
  if (certainty === "to_verify") return "待核查";
  return "线索";
}

function certaintyVariant(
  certainty: DiscussionTurn["certainty"],
): "success" | "warning" | "secondary" {
  if (certainty === "supported") return "success";
  if (certainty === "to_verify") return "warning";
  return "secondary";
}

function LinkedObjectList({ objects }: { objects: LinkedObject[] }) {
  if (objects.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {objects.map((object) => (
        <Badge key={`${object.type}-${object.label}`} variant="outline">
          {LINKED_OBJECT_LABELS[object.type]}：{object.label} · {object.status}
        </Badge>
      ))}
    </div>
  );
}

function TurnRecord({ turn }: { turn: DiscussionTurn }) {
  return (
    <div className="space-y-2 rounded-md border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="secondary">第 {turn.round} 轮</Badge>
        <Badge variant="outline">{TURN_LABELS[turn.kind]}</Badge>
        <span className="font-medium">{turn.speakerName}</span>
        <Badge variant={certaintyVariant(turn.certainty)}>{certaintyLabel(turn.certainty)}</Badge>
      </div>
      <p className="text-sm leading-6">{turn.content}</p>
      <p className="text-xs text-muted-foreground">
        来源引用：{turn.sourceRefs.length > 0 ? turn.sourceRefs.join("、") : "待补来源"}
      </p>
    </div>
  );
}

export function DiscussionDetail({ discussion }: Props) {
  return (
    <article className="space-y-5 rounded-md border bg-card p-5">
      <header className="space-y-3 border-b pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-primary">自由讨论记录</p>
            <h2 className="mt-1 break-words text-xl font-semibold">{discussion.title}</h2>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Badge variant="outline">synthetic</Badge>
            <Badge variant="secondary">not_persisted</Badge>
          </div>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">{discussion.trigger}</p>
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="text-xs text-muted-foreground">关联课题</p>
            <p className="mt-1 font-medium">{discussion.topic}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">讨论时间</p>
            <p className="mt-1 font-medium">
              {discussion.startedAt} - {discussion.endedAt}
            </p>
          </div>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">参与 Agent</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {discussion.participants.map((participant) => (
              <Badge key={participant.id} variant="secondary">
                {participant.name} · {participant.role}
              </Badge>
            ))}
          </div>
        </div>
        <LinkedObjectList objects={discussion.linkedObjects} />
      </header>

      <section className="space-y-3" aria-labelledby="discussion-transcript-heading">
        <div>
          <h3 id="discussion-transcript-heading" className="text-base font-semibold">
            完整讨论
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            展示可审阅的讨论记录，不展示模型内部隐藏思维链。
          </p>
        </div>
        <div className="space-y-2">
          {discussion.turns.map((turn) => (
            <TurnRecord key={turn.id} turn={turn} />
          ))}
        </div>
      </section>

      <section className="grid gap-4 border-t pt-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h3 className="text-base font-semibold">AI 纪要</h3>
          <p className="text-sm leading-6 text-muted-foreground">{discussion.summary.overview}</p>
          <ul className="list-disc space-y-1 pl-5 text-sm leading-6">
            {discussion.summary.keyPoints.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <p className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm leading-6">
            {discussion.summary.currentConclusion}
          </p>
        </div>
        <div className="space-y-4">
          <div>
            <h3 className="text-base font-semibold">未决分歧</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-muted-foreground">
              {discussion.summary.unresolvedDisagreements.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-base font-semibold">下一步建议</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-muted-foreground">
              {discussion.summary.actionItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <p className="border-t pt-3 text-xs text-muted-foreground">
        本记录属于 Agent 非组会自由讨论，不是正式组会纪要、PI 决策或已核查科研证据。
      </p>
    </article>
  );
}
