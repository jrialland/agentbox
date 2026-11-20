import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthCard } from "./AuthCard";
import { DashboardCard } from "./DashboardCard";
import { ListPage } from "./ListPage";

describe("page patterns", () => {
  it("renders the auth card brand and title", () => {
    render(
      <AuthCard title="Login" subtitle="Operator access">
        <span>form</span>
      </AuthCard>,
    );
    expect(screen.getByText("[AGENTBOX]▮")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Login" })).toBeInTheDocument();
    expect(screen.getByText("form")).toBeInTheDocument();
  });

  it("renders a list page header and children", () => {
    render(
      <ListPage title="Agents" actions={<button>New agent</button>}>
        <div>rows</div>
      </ListPage>,
    );
    expect(screen.getByRole("heading", { name: "Agents" })).toBeInTheDocument();
    expect(screen.getByText("rows")).toBeInTheDocument();
  });

  it("renders a dashboard card", () => {
    render(<DashboardCard label="Projects" value={3} hint="configured" />);
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("configured")).toBeInTheDocument();
  });
});
