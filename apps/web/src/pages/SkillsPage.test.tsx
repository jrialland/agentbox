import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, vi } from "vitest";

import * as endpoints from "../api/endpoints";
import { SkillsPage } from "./SkillsPage";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <SkillsPage />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

test("renders skills and scopes", async () => {
  vi.spyOn(endpoints, "fetchSkills").mockResolvedValue([
    { name: "code-review", description: "Review code", scope: "builtin" },
    { name: "my-skill", description: "Mine", scope: "user" },
  ] as never);
  renderPage();
  expect(
    await screen.findByRole("heading", { name: "Skills" }),
  ).toBeInTheDocument();
  expect(await screen.findByText("code-review")).toBeInTheDocument();
  expect(screen.getByText("my-skill")).toBeInTheDocument();
  expect(screen.getAllByText("builtin").length).toBeGreaterThan(0);
  expect(screen.getAllByText("user").length).toBeGreaterThan(0);
});

test("shows a retry state when skills fail to load", async () => {
  vi.spyOn(endpoints, "fetchSkills").mockRejectedValueOnce(new Error("boom"));
  renderPage();
  expect(await screen.findByText("Could not load skills")).toBeInTheDocument();
});
