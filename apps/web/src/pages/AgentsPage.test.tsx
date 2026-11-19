import { NATIVE_TOOLS } from "./AgentsPage";

test("lists the full filesystem toolset", () => {
  expect(NATIVE_TOOLS).toContain("delete_path");
  expect(NATIVE_TOOLS).toContain("read_media_file");
  expect(NATIVE_TOOLS).toContain("directory_tree");
  expect(NATIVE_TOOLS).toHaveLength(16);
});
