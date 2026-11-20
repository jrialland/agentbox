import { render } from "@testing-library/react";
import { RiHome5Line } from "@remixicon/react";
import { describe, expect, it } from "vitest";

import { Icon } from "./Icon";

describe("Icon", () => {
  it("renders an svg and is decorative by default", () => {
    const { container } = render(<Icon as={RiHome5Line} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  it("becomes labelled when a label is provided", () => {
    const { getByRole } = render(<Icon as={RiHome5Line} label="Home" />);
    expect(getByRole("img", { name: "Home" })).toBeInTheDocument();
  });
});
