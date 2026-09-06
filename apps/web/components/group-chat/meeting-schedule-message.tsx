"use client";

import { useState } from "react";

import { CalendarDays } from "lucide-react";

type Props = {
  onSave: (nextMeetingAt: string) => void;
};

/** 博士后气泡内的组会安排：单个 datetime-local 输入 + 保存。 */
export function MeetingScheduleMessage({ onSave }: Props) {
  const [value, setValue] = useState("");

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <CalendarDays className="h-4 w-4" aria-hidden />
        <span>安排下一次组会时间</span>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="datetime-local"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-label="组会时间"
          className="rounded border bg-background px-2 py-1 text-sm"
        />
        <button
          type="button"
          disabled={!value}
          onClick={() => {
            if (value) onSave(value);
          }}
          className="rounded bg-primary px-2.5 py-1 text-sm text-primary-foreground disabled:opacity-50"
        >
          保存
        </button>
      </div>
    </div>
  );
}
