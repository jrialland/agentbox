import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { vi } from "vitest";

import * as endpoints from "./endpoints";
import { useProjects } from "./queries";

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
