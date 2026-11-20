import mermaid from "mermaid";
import { useEffect, useState } from "react";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";

import { CopyButton } from "../design-system/primitives/CopyButton";
import "./markdown.css";

mermaid.initialize({ startOnLoad: false });

export function MermaidBlock({
  source,
  complete,
}: {
  source: string;
  complete: boolean;
}) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setSvg("");
    setFailed(false);
    if (!complete) return;
    let cancelled = false;
    const id = `mermaid-${Math.random().toString(36).slice(2)}`;
    (async () => {
      try {
        await mermaid.parse(source);
        const res = await mermaid.render(id, source);
        if (!cancelled) setSvg(res.svg);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        document.getElementById(id)?.remove();
      }
    })();
    return () => {
      cancelled = true;
      document.getElementById(id)?.remove();
    };
  }, [source, complete]);

  if (!complete) {
    return (
      <div className="mermaid-building" role="status">
        Diagram building.
      </div>
    );
  }

  if (failed) {
    return (
      <div className="mermaid-fallback">
        <p>Diagram could not be rendered</p>
        <pre>
          <code>{source}</code>
        </pre>
        <CopyButton value={source} label="Copy diagram" />
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="mermaid-building" role="status">
        Rendering diagram.
      </div>
    );
  }

  return (
    <div className="mermaid-block">
      <TransformWrapper>
        <TransformComponent>
          <div
            className="mermaid-canvas"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </TransformComponent>
      </TransformWrapper>
    </div>
  );
}
