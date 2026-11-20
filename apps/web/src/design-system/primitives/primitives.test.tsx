import { render, screen } from "@testing-library/react";
import { RiRobot2Line } from "@remixicon/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";
import { PageHeader } from "./PageHeader";
import { Panel } from "./Panel";
import { StatusChip } from "./StatusChip";

describe("surface primitives", () => {
  it("renders a page header with actions", () => {
    render(
      <PageHeader
        title="Agents"
        subtitle="2 configured"
        actions={<button>New agent</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "Agents" })).toBeInTheDocument();
    expect(screen.getByText("2 configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New agent" })).toBeInTheDocument();
  });

  it("renders an empty state", () => {
    render(
      <EmptyState
        icon={RiRobot2Line}
        title="No agents"
        description="Create your first agent."
      />,
    );
    expect(screen.getByText("No agents")).toBeInTheDocument();
    expect(screen.getByText("Create your first agent.")).toBeInTheDocument();
  });

  it("renders panel header and body", () => {
    render(
      <Panel>
        <Panel.Header>Projects</Panel.Header>
        <Panel.Body>content</Panel.Body>
      </Panel>,
    );
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("renders status tones", () => {
    render(<StatusChip tone="success">active</StatusChip>);
    expect(screen.getByText("active")).toHaveAttribute("data-tone", "success");
  });
});
