import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownBlock } from "./MarkdownBlock";

describe("MarkdownBlock", () => {
  it("renders styled block markdown and highlighted code", () => {
    render(
      <MarkdownBlock
        content={
          "# Title\n\n- one\n- two\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n```ts\nconst x = 1\n```"
        }
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeTruthy();
    expect(screen.getByRole("list")).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    const code = document.querySelector("pre code");
    expect(code?.textContent).toBe("const x = 1");
    expect(code?.querySelector(".hljs-keyword")).toBeTruthy();
  });

  it("copies fenced source from the code block button", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<MarkdownBlock content={"```js\nconst x = 1\n```"} />);

    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("const x = 1"));
  });
});
