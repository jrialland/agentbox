import { CloseButton, Tabs } from "@mantine/core";
import { AppRenderer } from "@mcp-ui/client";
import type {
  CallToolResult,
  ReadResourceResult,
} from "@modelcontextprotocol/sdk/types.js";
import { useEffect, useMemo, useState } from "react";

import { SANDBOX_URL } from "../config";
import type { AppTab } from "./apps";
import styles from "./chat-split.module.css";
import { callAppTool, readAppResource } from "./relay";

function toRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : undefined;
}

function AppView({ sessionId, tab }: { sessionId: string; tab: AppTab }) {
  const sandbox = useMemo(() => ({ url: new URL(SANDBOX_URL) }), []);
  return (
    <div className={styles.appView}>
      <AppRenderer
        toolName="app"
        toolResourceUri={tab.resourceUri}
        toolInput={toRecord(tab.toolInput)}
        toolResult={tab.toolResult as CallToolResult | undefined}
        sandbox={sandbox}
        hostCapabilities={{
          openLinks: {},
          serverTools: {},
          serverResources: {},
          logging: {},
        }}
        onReadResource={async (params) =>
          (await readAppResource(sessionId, tab, params.uri)) as ReadResourceResult
        }
        onCallTool={async (params) =>
          (await callAppTool(
            sessionId,
            tab,
            params.name,
            (params.arguments ?? {}) as Record<string, unknown>,
          )) as CallToolResult
        }
        onOpenLink={async ({ url }) => {
          window.open(url, "_blank", "noopener,noreferrer");
          return {};
        }}
        onError={(err) => console.error("[mcp-app]", err)}
      />
    </div>
  );
}

export function AppPanel({
  sessionId,
  tabs,
  onClose,
}: {
  sessionId: string;
  tabs: AppTab[];
  onClose: (id: string) => void;
}) {
  const [active, setActive] = useState<string | null>(tabs[0]?.id ?? null);

  useEffect(() => {
    if (tabs.length === 0) {
      setActive(null);
    } else if (!tabs.some((t) => t.id === active)) {
      setActive(tabs[0].id);
    }
  }, [tabs, active]);

  return (
    <div className={styles.panel} data-testid="app-panel">
      <Tabs value={active} onChange={setActive}>
        <Tabs.List>
          {tabs.map((tab, i) => (
            <Tabs.Tab
              key={tab.id}
              value={tab.id}
              rightSection={
                <CloseButton
                  component="span"
                  role="button"
                  size="xs"
                  aria-label="Close app"
                  onClick={(e) => {
                    e.stopPropagation();
                    onClose(tab.id);
                  }}
                />
              }
            >
              App {i + 1}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        {tabs.map((tab) => (
          <Tabs.Panel key={tab.id} value={tab.id} className={styles.panelBody}>
            <AppView sessionId={sessionId} tab={tab} />
          </Tabs.Panel>
        ))}
      </Tabs>
    </div>
  );
}

