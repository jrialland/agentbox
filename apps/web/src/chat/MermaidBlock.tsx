import {
  RiAddLine,
  RiFullscreenExitLine,
  RiFullscreenLine,
  RiRefreshLine,
  RiSubtractLine,
} from "@remixicon/react";
import mermaid from "mermaid";
import { useEffect, useRef, useState } from "react";
import {
  TransformComponent,
  TransformWrapper,
  useControls,
} from "react-zoom-pan-pinch";

import { CopyButton } from "../design-system/primitives/CopyButton";
import { IconButton } from "../design-system/icons/IconButton";
import "./markdown.css";

mermaid.initialize({ startOnLoad: false });

function MermaidToolbar({
  source,
  fullscreen,
  fullscreenAvailable,
  onToggleFullscreen,
}: {
  source: string;
  fullscreen: boolean;
  fullscreenAvailable: boolean;
  onToggleFullscreen: () => void;
}) {
  const { zoomIn, zoomOut, resetTransform } = useControls();
  return (
    <div className="mermaid-tools">
      <IconButton
        label="Zoom in"
        icon={RiAddLine}
        size={16}
        onClick={() => void zoomIn()}
      />
      <IconButton
        label="Zoom out"
        icon={RiSubtractLine}
        size={16}
        onClick={() => void zoomOut()}
      />
      <IconButton
        label="Reset zoom"
        icon={RiRefreshLine}
        size={16}
        onClick={() => void resetTransform()}
      />
      <IconButton
        label={fullscreen ? "Exit fullscreen" : "Enter fullscreen"}
        icon={fullscreen ? RiFullscreenExitLine : RiFullscreenLine}
        size={16}
        disabled={!fullscreenAvailable}
        onClick={onToggleFullscreen}
      />
      <CopyButton value={source} label="Copy diagram" />
    </div>
  );
}

export function MermaidBlock({
  source,
  complete,
}: {
  source: string;
  complete: boolean;
}) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const blockRef = useRef<HTMLDivElement>(null);
  const fullscreenAvailable =
    typeof document !== "undefined" && document.fullscreenEnabled;

  useEffect(() => {
    const onChange = () => {
      setFullscreen(document.fullscreenElement === blockRef.current);
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      if (document.fullscreenElement === blockRef.current) {
        void document.exitFullscreen().catch(() => undefined);
      }
    };
  }, []);

  async function toggleFullscreen() {
    const element = blockRef.current;
    if (!element || !fullscreenAvailable) return;
    try {
      if (document.fullscreenElement === element) {
        await document.exitFullscreen();
      } else {
        await element.requestFullscreen();
      }
    } catch {
      setFullscreen(false);
    }
  }

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
    <div className="mermaid-block" ref={blockRef}>
      <TransformWrapper>
        <MermaidToolbar
          source={source}
          fullscreen={fullscreen}
          fullscreenAvailable={fullscreenAvailable}
          onToggleFullscreen={() => void toggleFullscreen()}
        />
        <TransformComponent
          wrapperStyle={{ width: "100%" }}
          contentStyle={{ width: "100%" }}
        >
          <div
            className="mermaid-canvas"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </TransformComponent>
      </TransformWrapper>
    </div>
  );
}
