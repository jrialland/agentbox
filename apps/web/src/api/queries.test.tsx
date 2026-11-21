import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { vi } from "vitest";

import * as endpoints from "./endpoints";
import { useDeleteProject, useProjects, useTestProvider } from "./queries";

test("useProjects returns fetched data", async () => {
  vi.spyOn(endpoints, "fetchProjects").mockResolvedValue([
    { id: "p1", name: "P", path: "/x", owner_id: "u1", created_at: "t" },
  ] as never);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  const { result } = renderHook(() => useProjects(), { wrapper });
  await waitFor(() => expect(result.current.data?.length).toBe(1));
});


test("useTestProvider returns the test result", async () => {
  vi.spyOn(endpoints, "testProvider").mockResolvedValue({
    ok: true,
    latency_ms: 12,
    model_count: 2,
    sample_models: ["a", "b"],
    error: null,
  } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useTestProvider(), { wrapper });
  await act(async () => {
    const value = await result.current.mutateAsync({
      kind: "generic",
      models_url: "https://example.test/models",
    });
    expect(value.model_count).toBe(2);
  });
});

test("useDeleteProject invalidates projects and session queries", async () => {
  vi.spyOn(endpoints, "deleteProject").mockResolvedValue(undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  const { result } = renderHook(() => useDeleteProject(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync("p1");
  });

  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["projects"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["sessions"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["session"] });
});
