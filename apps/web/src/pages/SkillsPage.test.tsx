import { screen } from "@testing-library/react";
import { vi } from "vitest";

import { renderWithTheme } from "../test/render";

vi.mock("../api/queries", () => ({
  useSkills: () => ({
    data: [
      { name: "code-review", description: "Review code", scope: "builtin" },
      { name: "my-skill", description: "Mine", scope: "user" },
    ],
  }),
  useSaveSkill: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSkill: () => ({ mutateAsync: vi.fn() }),
}));

import { SkillsPage } from "./SkillsPage";

test("renders skills and scopes", () => {
  renderWithTheme(<SkillsPage />);
  expect(screen.getByRole("heading", { name: "Skills" })).toBeInTheDocument();
  expect(screen.getByText("code-review")).toBeInTheDocument();
  expect(screen.getByText("my-skill")).toBeInTheDocument();
  expect(screen.getAllByText("builtin").length).toBeGreaterThan(0);
  expect(screen.getAllByText("user").length).toBeGreaterThan(0);
});
