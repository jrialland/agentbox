import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const queries = vi.hoisted(() => ({
  useSkills: vi.fn(),
  useSaveSkill: vi.fn(),
  useDeleteSkill: vi.fn(),
}));

vi.mock("../api/queries", () => queries);

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
  queries.useSkills.mockReset().mockReturnValue({
    data: [{ name: "my-skill", description: "Mine", scope: "user" }],
    error: undefined,
    refetch: vi.fn(),
  });
  queries.useSaveSkill
    .mockReset()
    .mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

it("requires confirmation before deleting a skill", async () => {
  const remove = vi.fn().mockResolvedValue(undefined);
  queries.useDeleteSkill.mockReturnValue({
    mutateAsync: remove,
    isPending: false,
  });
  renderPage();

  fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
  const dialog = await screen.findByRole("dialog");
  expect(remove).not.toHaveBeenCalled();

  fireEvent.click(
    within(dialog).getByRole("button", { name: /^Delete$/ }),
  );
  await waitFor(() => expect(remove).toHaveBeenCalledWith("my-skill"));
});

it("keeps the dialog open and shows the error when deletion fails", async () => {
  const remove = vi.fn().mockRejectedValue(new Error("Skill is in use"));
  queries.useDeleteSkill.mockReturnValue({
    mutateAsync: remove,
    isPending: false,
  });
  renderPage();

  fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(
    within(dialog).getByRole("button", { name: /^Delete$/ }),
  );

  expect(await screen.findByText("Skill is in use")).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
