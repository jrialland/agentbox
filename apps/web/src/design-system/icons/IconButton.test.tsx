import { fireEvent, screen } from "@testing-library/react";
import { RiAddLine } from "@remixicon/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithTheme } from "../../test/render";
import { IconButton } from "./IconButton";

describe("IconButton", () => {
  it("exposes an accessible label and fires onClick", () => {
    const onClick = vi.fn();
    renderWithTheme(
      <IconButton label="New session" icon={RiAddLine} onClick={onClick} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "New session" }));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
