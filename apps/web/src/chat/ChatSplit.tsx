import { Drawer } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { useEffect, useRef, useState, type ReactNode } from "react";

import styles from "./chat-split.module.css";

const MIN = 32;
const MAX = 68;

function clamp(value: number) {
  return Math.min(MAX, Math.max(MIN, value));
}

export function ChatSplit({
  chat,
  app,
  appOpen,
}: {
  chat: ReactNode;
  app: ReactNode;
  appOpen: boolean;
}) {
  const [width, setWidth] = useState(50);
  const [sheetOpen, setSheetOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const isMobile = useMediaQuery("(max-width: 960px)");

  useEffect(() => {
    if (!appOpen) setSheetOpen(false);
    else if (isMobile) setSheetOpen(true);
  }, [appOpen, isMobile]);

  if (!appOpen) return <>{chat}</>;

  if (isMobile) {
    return (
      <>
        {chat}
        <button
          type="button"
          className={styles.openSheet}
          onClick={() => setSheetOpen(true)}
        >
          Open app
        </button>
        <Drawer
          opened={appOpen && sheetOpen}
          onClose={() => setSheetOpen(false)}
          position="right"
          size="100%"
          title="App panel"
        >
          <button
            type="button"
            className={styles.sheetClose}
            onClick={() => setSheetOpen(false)}
          >
            Close app panel
          </button>
          {app}
        </Drawer>
      </>
    );
  }

  function startDrag(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const move = (moveEvent: PointerEvent) => {
      const percent = ((moveEvent.clientX - rect.left) / rect.width) * 100;
      setWidth(clamp(percent));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  return (
    <div
      ref={containerRef}
      className={styles.split}
      style={{ gridTemplateColumns: `${width}% 10px minmax(0, 1fr)` }}
    >
      <div className={styles.chat}>{chat}</div>
      <div
        className={styles.divider}
        role="separator"
        aria-label="Resize app panel"
        aria-orientation="vertical"
        aria-valuemin={MIN}
        aria-valuemax={MAX}
        aria-valuenow={Math.round(width)}
        tabIndex={0}
        onPointerDown={startDrag}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setWidth((value) => clamp(value - 5));
          if (event.key === "ArrowRight") setWidth((value) => clamp(value + 5));
        }}
      />
      <div className={styles.app}>{app}</div>
    </div>
  );
}
