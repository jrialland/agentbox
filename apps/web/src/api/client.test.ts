import { vi } from "vitest";

import { ApiError } from "./errors";
import { authMiddleware, createApiFetch } from "./client";

test("authMiddleware adds bearer header", async () => {
  const mw = authMiddleware(() => "tok123");
  const request = new Request("http://x/");
  await mw.onRequest({ request });
  expect(request.headers.get("Authorization")).toBe("Bearer tok123");
});

test("authMiddleware leaves header off without token", async () => {
  const mw = authMiddleware(() => null);
  const request = new Request("http://x/");
  await mw.onRequest({ request });
  expect(request.headers.get("Authorization")).toBeNull();
});

test("network rejection becomes an ApiError with status 0", async () => {
  const wrapped = createApiFetch(async () => {
    throw new TypeError("fetch failed");
  });

  await expect(wrapped("http://x/")).rejects.toBeInstanceOf(ApiError);
  await expect(wrapped("http://x/")).rejects.toMatchObject({
    status: 0,
    detail: "Network request unavailable",
  });
});

test("successful responses pass through unchanged", async () => {
  const response = new Response("ok");
  const impl = vi.fn().mockResolvedValue(response);
  const wrapped = createApiFetch(impl);

  await expect(wrapped("http://x/")).resolves.toBe(response);
  expect(impl).toHaveBeenCalledTimes(1);
});
