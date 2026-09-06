"use client";

import { useEffect, useState } from "react";

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
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import {
  clearRuntimeSettings,
  getRuntimeSettings,
  saveRuntimeSettings,
  type RuntimeSettings,
} from "@/lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [provider, setProvider] = useState("openai-compatible");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const readableError = (err: unknown) =>
    err instanceof ApiError || err instanceof ApiConfigError
      ? err.message
      : "Runtime 设置请求失败，请稍后重试";

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const current = await getRuntimeSettings();
      setSettings(current);
      if (current.provider) setProvider(current.provider);
      if (current.base_url) setBaseUrl(current.base_url);
      if (current.model) setModel(current.model);
    } catch (err) {
      setError(readableError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const next = await saveRuntimeSettings({
        provider,
        base_url: baseUrl,
        model,
        api_key: apiKey,
      });
      setSettings(next);
      setApiKey("");
      setNotice("Runtime 配置已保存，API Key 仅保存在服务端进程内。");
    } catch (err) {
      setError(readableError(err));
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      setSettings(await clearRuntimeSettings());
      setApiKey("");
      setNotice("Runtime 配置已清除。");
    } catch (err) {
      setError(readableError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-2xl font-semibold tracking-tight">设置</h1>
      <Card className="mt-6">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Runtime API 配置</h2>
              <CardDescription>配置 Agent 使用的兼容 API 服务。密钥不会回显、写入日志或保存到数据库。</CardDescription>
            </div>
            <Badge variant={settings?.configured ? "success" : "outline"}>
              {loading ? "读取中" : settings?.configured ? "已配置" : "未配置"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label htmlFor="runtime-provider" className="text-sm font-medium">Provider</label>
              <Input id="runtime-provider" value={provider} onChange={(event) => setProvider(event.target.value)} />
            </div>
            <div className="space-y-1">
              <label htmlFor="runtime-model" className="text-sm font-medium">Model</label>
              <Input id="runtime-model" value={model} onChange={(event) => setModel(event.target.value)} />
            </div>
          </div>
          <div className="space-y-1">
            <label htmlFor="runtime-base-url" className="text-sm font-medium">Base URL</label>
            <Input id="runtime-base-url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" />
          </div>
          <div className="space-y-1">
            <label htmlFor="runtime-api-key" className="text-sm font-medium">API Key</label>
            <Input id="runtime-api-key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="输入新密钥；留空则保留已有密钥" autoComplete="new-password" />
          </div>
          {error !== null && <p className="text-sm text-destructive">{error}</p>}
          {notice !== null && <p className="text-sm text-emerald-700">{notice}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => void save()} disabled={saving || loading}>
              {saving ? "保存中…" : "保存 Runtime 配置"}
            </Button>
            <Button type="button" variant="outline" onClick={() => void clear()} disabled={saving || loading || !settings?.configured}>
              清除 Runtime 配置
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
