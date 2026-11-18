import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AppPanel } from "./AppPanel";
import { appTabFromSnapshot, type AppTab } from "./apps";

vi.mock("@mcp-ui/client", () => ({
  AppRenderer: () => <div data-testid="app-renderer" />,
}));

test("appTabFromSnapshot parses mcp-apps content", () => {
  const tab = appTabFromSnapshot({
    messageId: "m1",
    activityType: "mcp-apps",
    content: {
      resourceUri: "ui://x/a.html",
      toolInput: { a: 1 },
      result: { content: [] },
      serverId: "srv",
    },
  });
  expect(tab).toEqual({
    id: "m1",
    serverId: "srv",
    resourceUri: "ui://x/a.html",
    toolInput: { a: 1 },
    toolResult: { content: [] },
  });
});

test("appTabFromSnapshot ignores other activity types", () => {
  expect(
    appTabFromSnapshot({ messageId: "m", activityType: "other", content: {} }),
  ).toBeNull();
});

test("AppPanel renders a tab and closes it", () => {
  const tabs: AppTab[] = [
    {
      id: "m1",
      serverId: "srv",
      resourceUri: "ui://x/a.html",
      toolInput: {},
      toolResult: {},
    },
  ];
  const onClose = vi.fn();
  render(
    <MantineProvider>
      <AppPanel sessionId="s1" tabs={tabs} onClose={onClose} />
    </MantineProvider>,
  );
  expect(screen.getByText("App 1")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Close app"));
  expect(onClose).toHaveBeenCalledWith("m1");
});
