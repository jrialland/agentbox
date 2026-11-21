import { notifications } from "@mantine/notifications";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { useChat } from "./useChat";

vi.mock("./agent", () => ({
  streamChat: async function* () {
    yield {
      type: "CUSTOM",
      name: "mcp.warning",
      value: { server: "time", message: "boom" },
    };
    yield { type: "RUN_FINISHED" };
  },
}));

vi.mock("@mantine/notifications", () => ({
  notifications: { show: vi.fn() },
}));

describe("useChat MCP warnings", () => {
  test("shows a notification and finishes the run", async () => {
    const { result } = renderHook(() => useChat("http://test", null, "s1"));
    await act(async () => {
      await result.current.send("hi", {} as never);
    });
    await waitFor(() =>
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: expect.stringContaining("boom"),
        }),
      ),
    );
    expect(result.current.error).toBeNull();
  });
});
