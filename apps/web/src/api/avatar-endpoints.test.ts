import { vi } from "vitest";

import { resetAgentAvatar, uploadAgentAvatar } from "./endpoints";

test("uploadAgentAvatar PUTs multipart", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
  await uploadAgentAvatar(
    "bot",
    new File([new Uint8Array([1])], "a.png", { type: "image/png" }),
  );
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toContain("/agents/bot/avatar");
  expect(init.method).toBe("PUT");
  expect(init.body).toBeInstanceOf(FormData);
});

test("resetAgentAvatar DELETEs", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
  await resetAgentAvatar("bot");
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toContain("/agents/bot/avatar");
  expect(init.method).toBe("DELETE");
});
