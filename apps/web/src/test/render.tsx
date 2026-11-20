import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import { ThemeProvider } from "../design-system/theme/ThemeProvider";

function Wrapper({ children }: { children: ReactNode }) {
  return <ThemeProvider forceScheme="dark">{children}</ThemeProvider>;
}

export function renderWithTheme(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  return render(ui, { wrapper: Wrapper, ...options });
}
