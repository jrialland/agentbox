import { render, screen } from "@testing-library/react";
import { RiHome5Line } from "@remixicon/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RailItem } from "./RailItem";

describe("RailItem", () => {
  it("marks the active route", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <RailItem to="/" label="Home" icon={RiHome5Line} end />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
