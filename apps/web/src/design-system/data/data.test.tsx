import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable } from "./DataTable";

type Row = { id: string; name: string };

describe("DataTable", () => {
  it("renders headers and rows", () => {
    render(
      <DataTable<Row>
        rowKey={(row) => row.id}
        columns={[
          { key: "name", header: "Name", render: (row) => row.name },
        ]}
        rows={[{ id: "1", name: "alpha" }]}
      />,
    );
    expect(
      screen.getByRole("columnheader", { name: "Name" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "alpha" })).toBeInTheDocument();
  });
});
