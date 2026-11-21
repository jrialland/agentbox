import { describePermission } from "./permissionDescriptions";

test("prefers stored descriptions and falls back to built-ins", () => {
  expect(describePermission("projects:read", "Custom")).toBe("Custom");
  expect(describePermission("projects:read")).toContain("projects");
  expect(describePermission("custom:thing")).toBe("No description");
});
