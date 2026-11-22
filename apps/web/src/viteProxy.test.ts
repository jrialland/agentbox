import { describe, expect, it } from "vitest";

import { devProxy } from "../vite.config";

describe("vite dev proxy", () => {
  it("forwards llms.txt and llms sections to the backend", () => {
    expect(devProxy["^/llms\\.txt$"]).toEqual({
      target: "http://localhost:8000",
      changeOrigin: true,
    });
    expect(devProxy["^/llms/"]).toEqual({
      target: "http://localhost:8000",
      changeOrigin: true,
    });
  });
});
