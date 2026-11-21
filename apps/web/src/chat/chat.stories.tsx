import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { ActivityChips } from "./ActivityChips";
import { ChatSplit } from "./ChatSplit";
import { Composer } from "./Composer";
import { ErrorCard } from "./ErrorCard";
import { ForkBanner } from "./ForkBanner";
import { MarkdownBlock } from "./MarkdownBlock";
import { MessageTurn } from "./MessageTurn";
import { MermaidBlock } from "./MermaidBlock";
import { RunStatus } from "./RunStatus";
import { StatusChip } from "../design-system/primitives/StatusChip";

const markdown = `# Deployment notes

The build is **green** and the release is ready.

| Check | Result |
| --- | --- |
| Unit tests | pass |
| Build | pass |
| E2E | pass |

\`\`\`python
def health() -> dict[str, str]:
    return {"status": "ok"}
\`\`\`

1. Merge the branch.
2. Watch the deploy.
3. Verify the dashboard.

> Keep the rollback command handy.
`;

const activity = {
  status: "success",
  reasoning_ms: 1200,
  tools: [
    { name: "read_text_file", status: "success", duration_ms: 420 },
    { name: "run_tests", status: "success", duration_ms: 1800 },
  ],
};

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity } },
});

function ComposerStory() {
  const [value, setValue] = useState("Summarize the failing test and propose a fix.");
  return (
    <QueryClientProvider client={queryClient}>
      <Composer
        sessionId="story"
        value={value}
        setValue={setValue}
        mode="agent"
        setMode={() => {}}
        running={false}
        onSend={() => {}}
        onStop={() => {}}
        onSelectSkill={() => {}}
      />
    </QueryClientProvider>
  );
}

function LiveSegments() {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <details open style={{ borderLeft: "2px solid var(--ab-border)", paddingLeft: 12 }}>
        <summary style={{ color: "var(--ab-text-muted)" }}>Thought 1.2s</summary>
        <pre style={{ color: "var(--ab-text-muted)", whiteSpace: "pre-wrap" }}>
          Inspecting the failing test and the fixture setup.
        </pre>
      </details>
      <div
        style={{
          border: "1px solid var(--ab-border)",
          borderRadius: 4,
          padding: 12,
          display: "flex",
          gap: 12,
          alignItems: "center",
        }}
      >
        <code style={{ color: "var(--ab-amber)" }}>run_tests</code>
        <StatusChip tone="success">success</StatusChip>
        <span style={{ color: "var(--ab-text-muted)", marginLeft: "auto" }}>1.8s</span>
      </div>
      <MarkdownBlock content="The failure comes from a missing fixture. **Patch it** and rerun." />
    </div>
  );
}

const meta: Meta = {
  title: "Chat/States",
};

export default meta;
type Story = StoryObj;

export const Markdown: Story = {
  render: () => <MarkdownBlock content={markdown} />,
};

export const MermaidSuccess: Story = {
  render: () => (
    <MermaidBlock source={"graph TD; Request-->Agent; Agent-->Tool; Tool-->Answer"} complete />
  ),
};

export const MermaidFallback: Story = {
  render: () => <MermaidBlock source={"this is not a diagram"} complete />,
};

export const LiveSegmentOrder: Story = {
  render: () => <LiveSegments />,
};

export const ActivityCollapsed: Story = {
  render: () => <ActivityChips activity={activity} />,
};

export const ActivityExpanded: Story = {
  render: () => <ActivityChips activity={activity} defaultOpen />,
};

export const RunningStatus: Story = {
  render: () => <RunStatus running elapsedMs={2300} onStop={() => {}} />,
};

export const ComposerState: Story = {
  render: () => <ComposerStory />,
};

export const ForkState: Story = {
  render: () => <ForkBanner onCancel={() => {}} />,
};

export const Attachments: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 8 }}>
      <MessageTurn
        sessionId="story"
        agentName="Coder"
        message={{
          id: "u1",
          role: "user",
          content: "Review the attached notes.",
          attachments: [
            { id: "a1", filename: "notes.txt", media_type: "text/plain" },
            { id: "a2", filename: "diagram.png", media_type: "image/png" },
          ],
        }}
      />
      <MessageTurn
        sessionId="story"
        agentName="Coder"
        message={{
          id: "a1",
          role: "assistant",
          content: "I found two follow-ups in the notes.",
          activity,
        }}
      />
    </div>
  ),
};

export const ErrorState: Story = {
  render: () => (
    <ErrorCard
      error={{ code: "context_window", message: "Context window exceeded" }}
      onRetry={() => {}}
    />
  ),
};

export const SplitView: Story = {
  render: () => (
    <div style={{ height: 520 }}>
      <ChatSplit
        appOpen
        chat={
          <div style={{ padding: 12 }}>
            <MarkdownBlock content={markdown} />
          </div>
        }
        app={
          <div style={{ border: "1px solid var(--ab-border)", padding: 12 }}>
            MCP App placeholder
          </div>
        }
      />
    </div>
  ),
};
