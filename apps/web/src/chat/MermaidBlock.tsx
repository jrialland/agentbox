import mermaid from "mermaid";
import { useEffect, useState } from "react";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";

mermaid.initialize({ startOnLoad: false });

export function MermaidBlock({ source }: { source: string }) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${Math.random().toString(36).slice(2)}`;
    mermaid
      .render(id, source)
      .then((res) => {
        if (!cancelled) setSvg(res.svg);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  if (failed) return <pre className="mermaid-error">{source}</pre>;

  return (
    <div className="mermaid-block">
      <button type="button" onClick={() => navigator.clipboard.writeText(source)}>
        Copy diagram
      </button>
      <TransformWrapper>
        <TransformComponent>
          <div dangerouslySetInnerHTML={{ __html: svg }} />
        </TransformComponent>
      </TransformWrapper>
    </div>
  );
}
