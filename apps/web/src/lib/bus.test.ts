import { vi } from "vitest";

import { bus } from "./bus";

test("bus delivers typed events", () => {
  const handler = vi.fn();
  bus.on("theme:changed", handler);
  bus.emit("theme:changed", { scheme: "dark" });
  expect(handler).toHaveBeenCalledWith({ scheme: "dark" });
});
