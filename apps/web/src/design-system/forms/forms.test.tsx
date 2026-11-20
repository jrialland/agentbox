import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithTheme } from "../../test/render";
import { FormField } from "./FormField";
import { TextInput } from "./TextInput";

describe("form primitives", () => {
  it("renders a label, description, and error", () => {
    renderWithTheme(
      <FormField
        label="Name"
        description="Required"
        error="Name is required"
        required
      >
        <TextInput value="" onChange={() => {}} />
      </FormField>,
    );
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByText("Name is required")).toBeInTheDocument();
  });
});
