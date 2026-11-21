import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Workspace } from "./Workspace";
import styles from "./shell.module.css";

function renderWorkspace(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="*"
          element={
            <Workspace>
              <div>content</div>
            </Workspace>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Workspace", () => {
  it("locks scrolling for full-height session routes", () => {
    const { container } = renderWorkspace("/sessions/s1");
    const main = container.querySelector("main");
    expect(main?.className).toContain(styles.workspaceFullHeight);
  });

  it("keeps ordinary pages scrollable", () => {
    const { container } = renderWorkspace("/agents");
    const main = container.querySelector("main");
    expect(main?.className).not.toContain(styles.workspaceFullHeight);
  });
});
