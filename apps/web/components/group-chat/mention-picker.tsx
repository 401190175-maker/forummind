"use client";

import { cn } from "@/lib/utils";
import type { MentionTarget } from "./types";

const GROUP_LABELS: Record<MentionTarget["type"], string> = {
  all: "全体成员",
  role: "角色",
  member: "成员",
};

type Props = {
  /** 可 `@` 对象列表：全体、角色、成员（由父组件提供）。 */
  targets: MentionTarget[];
  /** 浮层是否打开；open=false 时不渲染列表。 */
  open: boolean;
  /** 选中任一对象时回调。 */
  onSelect: (target: MentionTarget) => void;
};

/**
 * `@` 对象选择浮层（design.md §2.1，tasks.md Task 2）。
 *
 * 只实现选择浮层：不包含输入框、不触发任务澄清、不启动 run。
 * 排版参考微信式 `@` 浮层，但只保留科研协作对象语义。
 */
export function MentionPicker({ targets, open, onSelect }: Props) {
  if (!open) {
    return null;
  }

  const groups: Array<{ type: MentionTarget["type"]; items: MentionTarget[] }> = (
    ["all", "role", "member"] as const
  )
    .map((type) => ({ type, items: targets.filter((t) => t.type === type) }))
    .filter((g) => g.items.length > 0);

  if (groups.length === 0) {
    return (
      <div className="rounded-md border bg-popover p-3 text-xs text-muted-foreground shadow-md">
        暂无可 @ 对象
      </div>
    );
  }

  return (
    <div className="max-h-64 overflow-y-auto rounded-md border bg-popover p-1 shadow-md">
      {groups.map((group) => (
        <div key={group.type} className="py-0.5">
          <p className="px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {GROUP_LABELS[group.type]}
          </p>
          {group.items.map((target) => (
            <button
              key={target.id}
              type="button"
              onClick={() => onSelect(target)}
              className={cn(
                "block w-full rounded px-2 py-1.5 text-left text-xs transition-colors",
                "hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              <span className="text-primary">@</span>
              <span className="ml-1 font-medium">{target.label}</span>
              {"role" in target && target.role && (
                <span className="ml-2 text-muted-foreground">{target.role}</span>
              )}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
