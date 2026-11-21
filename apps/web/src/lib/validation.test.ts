import { isAbsolutePath, requiredText } from "./validation";

test("requiredText trims and rejects blanks", () => {
  expect(requiredText("  hello ", "Name")).toBeNull();
  expect(requiredText("   ", "Name")).toBe("Name is required.");
});

test("isAbsolutePath accepts POSIX, drive, and UNC paths", () => {
  expect(isAbsolutePath("/tmp")).toBe(true);
  expect(isAbsolutePath("C:\\tmp")).toBe(true);
  expect(isAbsolutePath("\\\\server\\share")).toBe(true);
  expect(isAbsolutePath("relative/path")).toBe(false);
});
