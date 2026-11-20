import type { Meta, StoryObj } from "@storybook/react-vite";

import { Badge } from "../primitives/Badge";
import { DataTable } from "./DataTable";
import { ListRow } from "./ListRow";
import { Pagination } from "./Pagination";
import { TableToolbar } from "./TableToolbar";

type Row = { id: string; name: string; kind: string };

const rows: Row[] = [
  { id: "1", name: "deepseek-v4-pro", kind: "deepseek" },
  { id: "2", name: "deepseek-flash", kind: "deepseek" },
  { id: "3", name: "llama3", kind: "ollama" },
];

function DataDemo() {
  return (
    <div style={{ display: "grid", gap: 24 }}>
      <TableToolbar>
        <strong>Models</strong>
      </TableToolbar>
      <DataTable<Row>
        rowKey={(row) => row.id}
        columns={[
          { key: "name", header: "Model", render: (row) => row.name },
          {
            key: "kind",
            header: "Provider",
            render: (row) => <Badge tone="info">{row.kind}</Badge>,
          },
        ]}
        rows={rows}
      />
      <div>
        <ListRow
          title="alpha"
          subtitle="A long description that should wrap cleanly"
          meta={<Badge>builtin</Badge>}
        />
        <ListRow title="beta" subtitle="Another row" />
      </div>
      <Pagination page={1} totalPages={4} onChange={() => {}} />
    </div>
  );
}

const meta: Meta<typeof DataDemo> = {
  title: "Data/Overview",
  component: DataDemo,
};

export default meta;
type Story = StoryObj<typeof DataDemo>;
export const Default: Story = {};
