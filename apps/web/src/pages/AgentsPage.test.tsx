import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import {
  AgentsPage,
  NATIVE_TOOLS,
  TERMINAL_TOOLS,
  buildToolBindings,
} from "./AgentsPage";

const updateAgent = vi.hoisted(() => vi.fn());

vi.mock("../api/queries", () => ({
  useAgents: () => ({
    data: [
      {
        name: "coder",
        description: "desc",
        instructions: "inst",
        model_binding: { model: "m", provider: "p" },
        model_label: null,
        tool_bindings: [{ name: "read_text_file", required_flags: [] }],
        mode_definitions: [{ name: "agent", flags: { write: true } }],
      },
    ],
    error: null,
    refetch: vi.fn(),
  }),
  useCreateAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: updateAgent, isPending: false }),
  useDeleteAgent: () => ({ mutateAsync: vi.fn() }),
  useLabels: () => ({ data: [] }),
  useModels: () => ({ data: [] }),
  useProviders: () => ({ data: [] }),
  useResetAvatar: () => ({ mutateAsync: vi.fn() }),
  useUploadAvatar: () => ({ mutateAsync: vi.fn() }),
}));

test("lists the full native toolset", () => {
  expect(NATIVE_TOOLS).toContain("delete_path");
  expect(NATIVE_TOOLS).toContain("read_media_file");
  expect(NATIVE_TOOLS).toContain("directory_tree");
  expect(NATIVE_TOOLS).toContain("web_search");
  expect(NATIVE_TOOLS).toContain("fetch_url");
  expect(NATIVE_TOOLS).toContain("terminal");
  expect(NATIVE_TOOLS).toHaveLength(19);
  expect(TERMINAL_TOOLS).toEqual([
    "run_command",
    "list_jobs",
    "get_job_output",
    "kill_job",
  ]);
});

test("expands the terminal bundle to four bindings", () => {
  expect(buildToolBindings(["terminal", "read_text_file"])).toEqual([
    { name: "run_command" },
    { name: "list_jobs" },
    { name: "get_job_output" },
    { name: "kill_job" },
    { name: "read_text_file" },
  ]);
});

test("editing prefills the drawer after it mounted closed", () => {
  render(
    <MantineProvider>
      <AgentsPage />
    </MantineProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: "Edit" }));

  expect(screen.getByDisplayValue("coder")).toBeDisabled();
  expect(screen.getByLabelText("read_text_file")).toBeChecked();
});

test("saving an edited agent includes newly selected tools", async () => {
  updateAgent.mockResolvedValue({ name: "coder" });
  render(
    <MantineProvider>
      <AgentsPage />
    </MantineProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  fireEvent.click(screen.getByLabelText("write_file"));
  fireEvent.click(screen.getByRole("button", { name: "Save agent" }));

  await waitFor(() => expect(updateAgent).toHaveBeenCalledTimes(1));
  expect(updateAgent).toHaveBeenCalledWith({
    name: "coder",
    body: expect.objectContaining({
      tool_bindings: expect.arrayContaining([
        { name: "read_text_file" },
        { name: "write_file" },
      ]),
    }),
  });
});
