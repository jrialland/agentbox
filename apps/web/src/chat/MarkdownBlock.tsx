import hljs from "highlight.js/lib/common";
import type { ReactNode } from "react";
import { isValidElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { CopyButton } from "../design-system/primitives/CopyButton";
import { MermaidBlock } from "./MermaidBlock";
import "./markdown.css";

function CodeFence({ code, language }: { code: string; language: string }) {
  const known = language && hljs.getLanguage(language);
  const html = hljs.highlight(code, {
    language: known ? language : "plaintext",
  }).value;

  return (
    <figure className="md-code">
      <figcaption>
        <span>{known ? language : "text"}</span>
        <CopyButton value={code} label="Copy code" />
      </figcaption>
      <pre>
        <code
          className={`hljs language-${known ? language : "plaintext"}`}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </pre>
    </figure>
  );
}

function unclosedFence(content: string): { code: string; language: string } | null {
  let open: { code: string[]; language: string } | null = null;
  for (const line of content.split("\n")) {
    const match = /^```([\w-]*)/.exec(line);
    if (match) {
      open = open ? null : { code: [], language: match[1] };
    } else if (open) {
      open.code.push(line);
    }
  }
  return open
    ? { code: open.code.join("\n").replace(/\n$/, ""), language: open.language }
    : null;
}

function extractCode(children: ReactNode): {
  code: string;
  language: string;
} | null {
  if (!isValidElement<{ className?: string; children?: ReactNode }>(children)) {
    return null;
  }
  const className = children.props.className ?? "";
  const language = /language-([\w-]+)/.exec(className)?.[1] ?? "";
  return {
    code: String(children.props.children ?? "").replace(/\n$/, ""),
    language,
  };
}

export function MarkdownBlock({ content }: { content: string }) {
  const pending = unclosedFence(content);
  return (
    <div className="markdown-block">
      <div className="md-actions">
        <CopyButton value={content} label="Copy Markdown" />
      </div>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }) {
            const fence = extractCode(children);
            if (!fence) return <pre>{children}</pre>;
            if (fence.language === "mermaid") {
              const complete = !(
                pending?.language === "mermaid" && pending.code === fence.code
              );
              return <MermaidBlock source={fence.code} complete={complete} />;
            }
            return <CodeFence code={fence.code} language={fence.language} />;
          },
          a({ href, children }) {
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
