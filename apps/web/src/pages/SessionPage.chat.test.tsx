import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionPage } from "./SessionPage";

const state = vi.hoisted(() => ({
  messages: [] as Record<string, unknown>[],
  segments: [] as Record<string, unknown>[],
  running: false,
  error: null as string | null,
  send: vi.fn<() => Promise<void>>(async () => undefined),
  cancel: vi.fn(async () => undefined),
  reset: vi.fn(),
  closeApp: vi.fn(),
}));

const renameMock = vi.hoisted(() => vi.fn(async () => undefined));
const notifyMock = vi.hoisted(() => vi.fn());
vi.mock("@mantine/notifications", () => ({
  notifications: { show: notifyMock },
}));

vi.mock("../chat/useChat", () => ({
  useChat: () => ({
    segments: state.segments,
    appTabs: [],
    running: state.running,
    runStatus: state.running ? "running" : "idle",
    error: state.error,
    send: state.send,
    cancel: state.cancel,
    reset: state.reset,
    closeApp: state.closeApp,
  }),
}));

vi.mock("../api/queries", () => ({
  useMessages: () => ({ data: state.messages }),
  useSession: () => ({ data: { agent_name: "bot", title: "Release plan" } }),
  useSessionLsp: () => ({ data: { detected: [], active: [] } }),
  useSessionPlan: () => ({ data: { items: [] } }),
  useRenameSession: () => ({ mutateAsync: renameMock, isPending: false }),
  useSkills: () => ({ data: [] }),
  useSessionFiles: () => ({ data: [] }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/s1"]}>
          <Routes>
            <Route path="/sessions/:id" element={<SessionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

describe("SessionPage chat surface", () => {
  beforeEach(() => {
    state.messages = [];
    state.segments = [];
    state.running = false;
    state.error = null;
    state.send.mockClear();
    state.cancel.mockClear();
    state.reset.mockClear();
    renameMock.mockClear();
    notifyMock.mockClear();
  });

  it("shows the user's message optimistically while the run is in flight", async () => {
    let release: () => void = () => {};
    state.send = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    );
    renderPage();

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "hello there" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("hello there")).toBeInTheDocument();
    release();
    await waitFor(() => expect(state.reset).toHaveBeenCalled());
  });

  it("shows the last completed turn's context token usage", () => {
    state.messages = [
      { id: "u1", role: "user", content: "Question" },
      {
        id: "a1",
        role: "assistant",
        content: "Answer",
        parent_id: "u1",
        context_tokens: 5800,
      },
    ];
    renderPage();

    expect(screen.getByText("5.8k tokens")).toBeInTheDocument();
  });

  it("shows the session title in the header", () => {
    renderPage();

    expect(
      screen.getByRole("heading", { name: "Release plan" }),
    ).toBeTruthy();
  });

  it("reports a failed rename and keeps the editor open", async () => {
    renameMock.mockRejectedValueOnce(new Error("title too long"));
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    const input = screen.getByLabelText("Session title");
    fireEvent.change(input, { target: { value: "x".repeat(121) } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(notifyMock).toHaveBeenCalledWith({
        message: "Failed to rename session",
        color: "red",
      }),
    );
    expect(screen.getByLabelText("Session title")).toBeTruthy();
  });

  it("renders history activity chips, attachments and errors", () => {
    state.messages = [
      {
        id: "u1",
        role: "user",
        content: "Question",
        attachments: [{ id: "a1", filename: "notes.txt", media_type: "text/plain" }],
      },
      {
        id: "a1",
        role: "assistant",
        content: "Partial",
        parent_id: "u1",
        activity: {
          status: "cancelled",
          reasoning_ms: 1200,
          tools: [{ name: "read", status: "success", duration_ms: 420 }],
        },
      },
    ];
    renderPage();

    expect(screen.getByText("Reasoning 1.2s")).toBeTruthy();
    expect(screen.getByRole("link", { name: /notes\.txt/ })).toBeTruthy();
    expect(screen.getByText("cancelled")).toBeTruthy();
  });

  it("keeps live segments in event order", () => {
    state.messages = [];
    state.segments = [
      {
        id: "t1",
        kind: "text",
        messageId: "t1",
        text: "live answer",
        status: "done",
      },
      {
        id: "c1",
        kind: "tool",
        toolCallId: "c1",
        name: "read_file",
        args: "{}",
        status: "success",
        startedAt: 0,
        endedAt: 420,
      },
      {
        id: "r1",
        kind: "reasoning",
        text: "hidden",
        status: "done",
        startedAt: 0,
        endedAt: 1200,
      },
    ];
    const { container } = renderPage();

    const html = container.innerHTML;
    expect(html.indexOf("live answer")).toBeLessThan(html.indexOf("read_file"));
    expect(html.indexOf("read_file")).toBeLessThan(html.indexOf("Thought 1.2s"));
  });

  it("retries from the failed assistant turn without a new user turn", async () => {
    state.messages = [
      { id: "u1", role: "user", content: "Question" },
      {
        id: "a1",
        role: "assistant",
        content: "Partial",
        parent_id: "u1",
        activity: {
          status: "error",
          error: { code: 500, message: "provider down" },
        },
      },
    ];
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(state.send).toHaveBeenCalledWith(
        "Question",
        expect.objectContaining({ retryTurnId: "a1" }),
      ),
    );
  });

  it("stops a running turn", () => {
    state.running = true;
    renderPage();

    const stops = screen.getAllByRole("button", { name: "Stop" });
    expect(stops.length).toBeGreaterThan(0);
    fireEvent.click(stops[0]);
    expect(state.cancel).toHaveBeenCalled();
  });
});

