"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { GroupChatWizard } from "@/components/group-chat-wizard/wizard";
import { deleteGroupChat, listGroupChats } from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import {
  recordFromResponse,
  type GroupChatRecord,
  useGroupChatStore,
} from "@/lib/stores/group-chat-store";

function readableError(error: unknown): string {
  if (error instanceof ApiConfigError || error instanceof ApiError) {
    return error.message;
  }
  return "读取课题组列表时发生未知错误";
}

function GroupChatCards({
  records,
  onDelete,
  deletingId,
}: {
  records: GroupChatRecord[];
  onDelete: (record: GroupChatRecord) => void;
  deletingId: string | null;
}) {
  return (
    <div className="mt-6 space-y-3">
      {records.map((record) => (
        <Card key={record.id}>
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base">{record.topicName}</CardTitle>
                <CardDescription className="mt-1">{record.topicSummary}</CardDescription>
              </div>
              <Badge variant="outline">{record.members.length} 名成员</Badge>
            </div>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-0">
            <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
              <Badge variant="secondary">data_space = {record.dataSpace}</Badge>
              <Badge variant="secondary">persistence = {record.persistence}</Badge>
              <Badge variant="secondary">agent_automation = {record.agentAutomation}</Badge>
              <Badge variant="secondary">project_phase = {record.projectPhase}</Badge>
              {record.meetingSchedule !== null && (
                <Badge variant="outline">下次组会已置顶</Badge>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                asChild
              >
                <a href={`/groups/${record.id}`}>{record.topicName}</a>
              </Button>
              <Button
                variant="destructive"
                onClick={() => onDelete(record)}
                disabled={deletingId === record.id}
              >
                {deletingId === record.id ? "删除中…" : "删除课题组"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function GroupChatsPage() {
  const [view, setView] = useState<"list" | "wizard">("list");
  const cacheRecords = useGroupChatStore((s) => s.records);
  const hydrate = useGroupChatStore((s) => s.hydrate);
  const replaceFromServer = useGroupChatStore((s) => s.replaceFromServer);
  const [serverRecords, setServerRecords] = useState<GroupChatRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [serverError, setServerError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    hydrate();
    let active = true;

    setLoading(true);
    setServerError(null);
    setServerRecords(null);
    const timer = window.setTimeout(() => {
      void listGroupChats(query)
        .then((responses) => {
          if (!active) return;
          if (query.trim() === "") replaceFromServer(responses);
          setServerRecords(responses.map(recordFromResponse));
        })
        .catch((error: unknown) => {
          if (active) setServerError(readableError(error));
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 150);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [hydrate, query, replaceFromServer]);

  const handleDelete = async (record: GroupChatRecord) => {
    if (!window.confirm(`确认删除课题组“${record.topicName}”？此操作会清理其消息、运行和产物记录。`)) {
      return;
    }
    setDeletingId(record.id);
    setServerError(null);
    try {
      await deleteGroupChat(record.id);
      useGroupChatStore.getState().removeCachedGroupChat(record.id);
      setServerRecords((current) => current?.filter((item) => item.id !== record.id) ?? current);
    } catch (error) {
      setServerError(readableError(error));
    } finally {
      setDeletingId(null);
    }
  };

  if (view === "wizard") {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <GroupChatWizard onClose={() => setView("list")} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">课题组</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            搜索、浏览或创建你的 AI 科研课题组
          </p>
        </div>
        <Button onClick={() => setView("wizard")}>创建课题组</Button>
      </div>

      <div className="relative mt-6">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="搜索课题组名称、概述或成员…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="搜索课题组"
        />
      </div>

      {loading && cacheRecords.length === 0 ? (
        <Card className="mt-6">
          <CardContent className="py-8 text-sm text-muted-foreground">正在读取服务端课题组列表…</CardContent>
        </Card>
      ) : loading || serverError !== null ? (
        <>
          {serverError !== null && (
            <Card className="mt-6 border-destructive/50">
              <CardHeader>
                <CardTitle>课题组读取失败</CardTitle>
                <CardDescription>{serverError}</CardDescription>
              </CardHeader>
            </Card>
          )}
          {cacheRecords.length > 0 && (
            <>
              <p className="mt-6 text-sm text-muted-foreground">
                本地缓存，服务端未确认
              </p>
              <GroupChatCards records={cacheRecords} onDelete={handleDelete} deletingId={deletingId} />
            </>
          )}
        </>
      ) : serverRecords !== null && serverRecords.length === 0 ? (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>{query.trim() ? "没有匹配的课题组" : "暂无课题组"}</CardTitle>
            <CardDescription>
              {query.trim()
                ? "请尝试其他名称、概述或成员关键词。"
                : "点击右上角“创建课题组”，通过三步向导建立你的第一个 AI 课题组。"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant="secondary">demo 数据空间 · synthetic</Badge>
          </CardContent>
        </Card>
      ) : serverRecords !== null ? (
        <GroupChatCards records={serverRecords} onDelete={handleDelete} deletingId={deletingId} />
      ) : null}
    </div>
  );
}
