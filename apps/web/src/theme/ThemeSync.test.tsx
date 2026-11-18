import { MantineProvider } from "@mantine/core";
import { render } from "@testing-library/react";

import { ThemeSync } from "./ThemeSync";

test("sets data-theme on documentElement", () => {
  render(
    <MantineProvider defaultColorScheme="light">
      <ThemeSync />
    </MantineProvider>,
  );
  expect(document.documentElement.dataset.theme).toBe("light");
});
