import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { MermaidBlock } from "./MermaidBlock";

export function MarkdownBlock({ content }: { content: string }) {
  return (
    <div className="markdown-block">
      <button
        type="button"
        className="copy-source"
        onClick={() => navigator.clipboard.writeText(content)}
      >
        Copy Markdown
      </button>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code(props) {
            const { className, children } = props;
            const lang = /language-(\w+)/.exec(className ?? "")?.[1];
            if (lang === "mermaid") {
              return <MermaidBlock source={String(children).replace(/\n$/, "")} />;
            }
            return <code className={className}>{children}</code>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
