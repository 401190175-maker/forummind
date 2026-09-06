"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { FlaskConical, Bot, MessageSquare, Settings } from "lucide-react";

import { cn } from "@/lib/utils";
import { useApiStatusStore } from "@/lib/stores/api-status-store";
import { Separator } from "@/components/ui/separator";

const NAV_ITEMS = [
  { href: "/", label: "课题组", icon: FlaskConical },
  { href: "/plaza", label: "智能体广场", icon: Bot },
  { href: "/chatrooms", label: "聊天室", icon: MessageSquare },
];

function ApiStatusDot() {
  const status = useApiStatusStore((s) => s.status);

  const render = (() => {
    switch (status.kind) {
      case "checking":
        return { dot: "bg-muted-foreground animate-pulse", text: "检查中…" };
      case "connected":
        return { dot: "bg-ok", text: `API 已连接（${status.environment}）` };
      case "http-error":
        return { dot: "bg-destructive", text: `API 错误 HTTP ${status.status}` };
      case "missing-config":
        return { dot: "bg-warn", text: "配置缺失：未设置 NEXT_PUBLIC_API_BASE_URL" };
      case "disconnected":
        return { dot: "bg-destructive", text: "API 未连接" };
    }
  })();

  return (
    <div className="flex items-center gap-2 px-4 py-2 text-xs text-muted-foreground" title={render.text}>
      <span className={cn("size-2 shrink-0 rounded-full", render.dot)} />
      <span className="hidden truncate md:block">{render.text}</span>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const check = useApiStatusStore((s) => s.check);

  useEffect(() => {
    void check();
  }, [check]);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/" || pathname.startsWith("/groups");
    return pathname.startsWith(href);
  };

  return (
    <aside className="flex h-full w-16 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground md:w-60">
      <div className="flex items-center gap-2 px-4 py-4">
        <FlaskConical className="size-5 text-primary" />
        <span className="hidden text-sm font-semibold tracking-wide text-sidebar-accent-foreground md:inline">
          ForumMind
        </span>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-2">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}
              className={cn(
                "flex items-center justify-center gap-3 rounded-md px-3 py-2 text-sm transition-colors md:justify-start",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon className="size-4" />
              <span className="sr-only md:not-sr-only">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="space-y-1 border-t border-sidebar-border px-2 py-2">
        <Link
          href="/settings"
          title="设置"
          className={cn(
            "flex items-center justify-center gap-3 rounded-md px-3 py-2 text-sm transition-colors md:justify-start",
            pathname === "/settings"
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
          )}
        >
          <Settings className="size-4" />
          <span className="sr-only md:not-sr-only">设置</span>
        </Link>
        <Separator className="bg-sidebar-border" />
        <ApiStatusDot />
      </div>
    </aside>
  );
}
