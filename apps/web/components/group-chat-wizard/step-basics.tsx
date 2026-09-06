"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { isNonEmpty } from "./validation";
import type { WizardDraft } from "./types";

type Props = {
  draft: WizardDraft;
  onChange: (patch: Partial<WizardDraft>) => void;
  onNext: () => void;
  onCancel: () => void;
};

export function StepBasics({ draft, onChange, onNext, onCancel }: Props) {
  const [nameError, setNameError] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const handleNext = () => {
    const nameOk = isNonEmpty(draft.topicName);
    const summaryOk = isNonEmpty(draft.topicSummary);
    setNameError(nameOk ? null : "课题名称不能为空");
    setSummaryError(summaryOk ? null : "课题概述不能为空");
    if (nameOk && summaryOk) {
      onNext();
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>基础设置</CardTitle>
        <CardDescription>只包含两个必填信息：课题名称与课题概述。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="topic-name" className="text-sm font-medium">
            课题名称 <span className="text-destructive">*</span>
          </label>
          <Input
            id="topic-name"
            value={draft.topicName}
            placeholder="例：废弃泥浆基泡沫混凝土强度与孔结构研究"
            aria-invalid={nameError !== null}
            className={cn(nameError !== null && "border-destructive")}
            onChange={(e) => {
              onChange({ topicName: e.target.value });
              if (nameError !== null) setNameError(null);
            }}
          />
          {nameError !== null && <p className="text-xs text-destructive">{nameError}</p>}
        </div>
        <div className="space-y-1.5">
          <label htmlFor="topic-summary" className="text-sm font-medium">
            课题概述 <span className="text-destructive">*</span>
          </label>
          <Textarea
            id="topic-summary"
            rows={4}
            value={draft.topicSummary}
            placeholder="描述研究背景、目标、现象与约束…"
            aria-invalid={summaryError !== null}
            className={cn(summaryError !== null && "border-destructive")}
            onChange={(e) => {
              onChange({ topicSummary: e.target.value });
              if (summaryError !== null) setSummaryError(null);
            }}
          />
          {summaryError !== null && (
            <p className="text-xs text-destructive">{summaryError}</p>
          )}
        </div>
      </CardContent>
      <CardFooter className="justify-between">
        <Button variant="ghost" onClick={onCancel}>
          取消
        </Button>
        <Button onClick={handleNext}>下一步</Button>
      </CardFooter>
    </Card>
  );
}
