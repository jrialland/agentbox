import { firstFieldError, isAbsolutePath, requiredText } from "./validation";

test("requiredText trims and rejects blanks", () => {
  expect(requiredText("  hello ", "Name")).toBeNull();
  expect(requiredText("   ", "Name")).toBe("Name is required.");
});

test("firstFieldError maps a named server field", () => {
  expect(
    firstFieldError({ name: "name is required", path: "path is invalid" }, "name"),
  ).toBe("name is required");
  expect(firstFieldError({ name: "name is required" }, "path")).toBeUndefined();
  expect(firstFieldError(undefined, "name")).toBeUndefined();
});

test("isAbsolutePath accepts POSIX, drive, and UNC paths", () => {
  expect(isAbsolutePath("/tmp")).toBe(true);
  expect(isAbsolutePath("C:\\tmp")).toBe(true);
  expect(isAbsolutePath("\\\\server\\share")).toBe(true);
  expect(isAbsolutePath("relative/path")).toBe(false);
});
