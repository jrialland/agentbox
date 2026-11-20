import { NATIVE_TOOLS, TERMINAL_TOOLS, buildToolBindings } from "./AgentsPage";

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
