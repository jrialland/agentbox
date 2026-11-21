import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { Button } from "../primitives/Button";
import { ConfirmDialog } from "./ConfirmDialog";
import { Drawer } from "./Drawer";
import { Modal } from "./Modal";

function OverlaysDemo() {
  const [open, setOpen] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [typedConfirm, setTypedConfirm] = useState(false);

  return (
    <div style={{ display: "flex", gap: 12 }}>
      <Button onClick={() => setOpen(true)}>Open modal</Button>
      <Button variant="light" onClick={() => setDrawer(true)}>
        Open drawer
      </Button>
      <Button color="danger" onClick={() => setConfirm(true)}>
        Confirm delete
      </Button>
      <Button color="danger" onClick={() => setTypedConfirm(true)}>
        Confirm with typing
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title="Modal demo">
        <p>Modal content</p>
      </Modal>
      <Drawer opened={drawer} onClose={() => setDrawer(false)} title="Drawer demo">
        <p>Drawer content</p>
      </Drawer>
      <ConfirmDialog
        opened={confirm}
        title="Delete project?"
        description="This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={() => setConfirm(false)}
        onClose={() => setConfirm(false)}
      />
      <ConfirmDialog
        opened={typedConfirm}
        title="Delete project?"
        description="This permanently deletes the project and its sessions."
        confirmLabel="Delete"
        danger
        requireText="Demo"
        onConfirm={() => setTypedConfirm(false)}
        onClose={() => setTypedConfirm(false)}
      />
    </div>
  );
}

const meta: Meta<typeof OverlaysDemo> = {
  title: "Overlays/Overview",
  component: OverlaysDemo,
};

export default meta;
type Story = StoryObj<typeof OverlaysDemo>;
export const Default: Story = {};
