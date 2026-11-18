import { authMiddleware } from "./client";

test("authMiddleware adds bearer header", async () => {
  const mw = authMiddleware("tok123");
  const request = new Request("http://x/");
  await mw.onRequest({ request });
  expect(request.headers.get("Authorization")).toBe("Bearer tok123");
});

test("authMiddleware leaves header off without token", async () => {
  const mw = authMiddleware(null);
  const request = new Request("http://x/");
  await mw.onRequest({ request });
  expect(request.headers.get("Authorization")).toBeNull();
});
