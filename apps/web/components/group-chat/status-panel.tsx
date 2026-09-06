"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Props = {
  /** 群聊成员。 */
  members: Array<{ id: string; displayName: string; status: string }>;
  /** run 是否进行中（黄灯工作中）。 */
  runActive?: boolean;
  /** 是否处于 meeting 阶段（红灯组会/讨论中）。 */
  meetingActive?: boolean;
  /** 当前课题阶段（demo 文案）。 */
  projectPhaseLabel?: string;
  /** 关闭状态栏。 */
  onClose: () => void;
};

type Light = "idle" | "working" | "meeting" | "pending";

const LIGHT_CLASS: Record<Light, string> = {
  idle: "bg-emerald-500",
  working: "bg-yellow-500",
  meeting: "bg-red-500",
  pending: "bg-muted-foreground/50",
};

const LIGHT_LABEL: Record<Light, string> = {
  idle: "空闲",
  working: "工作中",
  meeting: "组会/讨论中",
  pending: "待配置",
};

/**
 * 可展开状态栏（design.md §7.9，tasks.md Task 6）。
 *
 * 成员状态灯：绿灯空闲 / 黄灯工作中 / 红灯组会或讨论中；
 * pending_generation 成员显示待配置。展示当前课题阶段与课题组动态 demo 摘要。
 * 不引入真实状态 API，状态从当前 record / run snapshot 推导并标注 demo。
 */
export function StatusPanel({
  members,
  runActive = false,
  meetingActive = false,
  projectPhaseLabel = "课题形成阶段（demo）",
  onClose,
}: Props) {
  const lightFor = (member: { status: string }): Light => {
    if (member.status === "pending_generation") return "pending";
    if (meetingActive) return "meeting";
    if (runActive) return "working";
    return "idle";
  };

  const activeCount = members.filter((m) => m.status === "active").length;

  return (
    <div className="rounded-md border bg-card p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-sm font-medium">状态栏</p>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          关闭
        </button>
      </div>

      <div className="mb-3 space-y-1">
        {members.map((member) => {
          const light = lightFor(member);
          return (
            <div
              key={member.id}
              className="flex items-center justify-between rounded border bg-muted/20 px-2.5 py-1.5 text-xs"
            >
              <span className="flex items-center gap-2">
                <span
                  className={cn("h-2.5 w-2.5 rounded-full", LIGHT_CLASS[light])}
                  aria-hidden
                />
                <span className="font-medium">{member.displayName}</span>
              </span>
              <span className="text-muted-foreground">{LIGHT_LABEL[light]}</span>
            </div>
          );
        })}
      </div>

      <div className="space-y-1 border-t pt-2 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">当前课题阶段：</span>
          {projectPhaseLabel}
        </p>
        <p>
          <span className="font-medium text-foreground">课题组动态（demo 摘要）：</span>
        </p>
        <ul className="list-disc space-y-0.5 pl-5">
          <li>暂无新交付文件（demo）</li>
          <li>暂无新聊天室自由讨论记录（demo）</li>
          <li>
            成员状态概览：{activeCount} 名成员空闲（绿灯）
            {members.some((m) => m.status === "pending_generation") &&
              "，其余成员待生成（待配置）"}
          </li>
          {meetingActive && <li>当前处于组会阶段，成员状态为组会/讨论中（红灯）</li>}
        </ul>
        <div className="flex flex-wrap gap-1.5 pt-1">
          <Badge variant="outline">状态 API 未接入（demo 推导）</Badge>
        </div>
      </div>
    </div>
  );
}
