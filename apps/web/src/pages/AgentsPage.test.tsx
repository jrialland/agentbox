import { NATIVE_TOOLS } from "./AgentsPage";

test("lists the full native toolset", () => {
  expect(NATIVE_TOOLS).toContain("delete_path");
  expect(NATIVE_TOOLS).toContain("read_media_file");
  expect(NATIVE_TOOLS).toContain("directory_tree");
  expect(NATIVE_TOOLS).toContain("web_search");
  expect(NATIVE_TOOLS).toContain("fetch_url");
  expect(NATIVE_TOOLS).toHaveLength(18);
});
