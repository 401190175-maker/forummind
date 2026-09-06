import { Fragment, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import type { MarkdownDocument } from "@/lib/demo-discussions";

type Props = {
  document: MarkdownDocument;
};

type Block =
  | { type: "heading"; level: number; content: string }
  | { type: "paragraph"; content: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; content: string }
  | { type: "code"; content: string };

function isSpecialLine(line: string): boolean {
  return (
    /^#{1,3}\s+/.test(line) ||
    /^[-*]\s+/.test(line) ||
    /^\d+\.\s+/.test(line) ||
    /^>\s?/.test(line) ||
    line.trim() === "```"
  );
}

function parseMarkdown(content: string): Block[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (line.trim() === "") {
      index += 1;
      continue;
    }

    if (line.trim() === "```") {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && lines[index].trim() !== "```") {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: "code", content: codeLines.join("\n") });
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, content: heading[2] });
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
      const ordered = /^\d+\.\s+/.test(line);
      const items: string[] = [];
      while (index < lines.length) {
        const item = ordered
          ? lines[index].match(/^\d+\.\s+(.+)$/)
          : lines[index].match(/^[-*]\s+(.+)$/);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "quote", content: quoteLines.join(" ") });
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() !== "" && !isSpecialLine(lines[index])) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push({ type: "paragraph", content: paragraphLines.join(" ") });
  }

  return blocks;
}

function renderBlock(block: Block, index: number): ReactNode {
  switch (block.type) {
    case "heading": {
      const className =
        block.level === 1
          ? "text-xl font-semibold"
          : block.level === 2
            ? "text-base font-semibold"
            : "text-sm font-semibold";
      return (
        <h2 key={index} className={className}>
          {block.content}
        </h2>
      );
    }
    case "paragraph":
      return (
        <p key={index} className="text-sm leading-6 text-foreground/90">
          {block.content}
        </p>
      );
    case "list": {
      const List = block.ordered ? "ol" : "ul";
      return (
        <List key={index} className="space-y-1 pl-5 text-sm leading-6 text-foreground/90">
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </List>
      );
    }
    case "quote":
      return (
        <blockquote key={index} className="border-l-2 border-primary/50 pl-3 text-sm text-muted-foreground">
          {block.content}
        </blockquote>
      );
    case "code":
      return (
        <pre
          key={index}
          className="overflow-x-auto rounded-md border bg-muted/40 p-3 font-mono text-xs leading-5 text-muted-foreground"
        >
          <code>{block.content}</code>
        </pre>
      );
  }
}

export function MarkdownPreview({ document }: Props) {
  const blocks = parseMarkdown(document.content);

  return (
    <section className="space-y-4 rounded-md border bg-card/70 p-4" aria-label="Markdown 文件预览">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-3">
        <div className="min-w-0">
          <h2 className="break-words text-base font-semibold">{document.title}</h2>
          <p className="mt-1 text-xs text-muted-foreground">来源：{document.sourceLabel}</p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Badge variant="outline">{document.dataSpace}</Badge>
          <Badge variant="secondary">{document.persistence}</Badge>
        </div>
      </div>
      {blocks.length > 0 ? (
        <div className="space-y-4">{blocks.map((block, index) => <Fragment key={index}>{renderBlock(block, index)}</Fragment>)}</div>
      ) : (
        <p className="text-sm text-muted-foreground">没有可预览内容。</p>
      )}
      <p className="border-t pt-3 text-xs text-muted-foreground">
        这是 synthetic demo Markdown，不是已落盘的真实文件。
      </p>
    </section>
  );
}
