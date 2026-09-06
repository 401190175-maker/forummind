import { Badge } from "@/components/ui/badge";
import type { DiscussionTurn } from "@/lib/demo-discussions";
import { cn } from "@/lib/utils";

type Props = {
  turns: DiscussionTurn[];
};

const CHAIN_STAGES: Array<{ kind: DiscussionTurn["kind"]; label: string }> = [
  { kind: "question", label: "问题" },
  { kind: "viewpoint", label: "观点" },
  { kind: "evidence", label: "证据" },
  { kind: "challenge", label: "质疑" },
  { kind: "response", label: "回应" },
  { kind: "revision", label: "修订" },
  { kind: "conclusion", label: "结论" },
];

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

export function StructuredChain({ turns }: Props) {
  return (
    <section className="space-y-4" aria-labelledby="structured-chain-heading">
      <div>
        <h2 id="structured-chain-heading" className="text-base font-semibold">
          结构化讨论链路
        </h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          这是可审阅的记录脉络，不是模型内部隐藏思维链。
        </p>
      </div>

      <div className="space-y-3">
        {CHAIN_STAGES.map((stage, index) => {
          const stageTurns = turns
            .filter((turn) => turn.kind === stage.kind)
            .sort((left, right) => left.round - right.round);
          const isLast = index === CHAIN_STAGES.length - 1;

          return (
            <div key={stage.kind} className="grid grid-cols-[auto_1fr] gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    "flex size-7 items-center justify-center rounded-full border text-xs font-semibold",
                    stageTurns.length > 0
                      ? "border-primary/60 bg-primary/10 text-primary"
                      : "border-border text-muted-foreground",
                  )}
                >
                  {index + 1}
                </span>
                {!isLast && <span className="mt-1 h-full min-h-6 w-px bg-border" aria-hidden="true" />}
              </div>

              <div className="min-w-0 space-y-2 pb-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">{stage.label}</h3>
                  {stageTurns.length === 0 && <Badge variant="outline">尚未记录</Badge>}
                </div>
                {stageTurns.length > 0 ? (
                  stageTurns.map((turn) => (
                    <div key={turn.id} className="space-y-2 rounded-md border bg-muted/20 p-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="font-medium">{turn.speakerName}</span>
                        <Badge variant={certaintyVariant(turn.certainty)}>
                          {certaintyLabel(turn.certainty)}
                        </Badge>
                        <span className="text-muted-foreground">第 {turn.round} 轮</span>
                      </div>
                      <p className="text-sm leading-6">{turn.content}</p>
                      <p className="break-words text-xs text-muted-foreground">
                        来源引用：{turn.sourceRefs.length > 0 ? turn.sourceRefs.join("、") : "待补来源"}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">该阶段尚未形成可审阅记录。</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
