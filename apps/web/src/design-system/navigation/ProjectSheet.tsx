import { Drawer } from "../overlays/Drawer";
import { ProjectPanel } from "./ProjectPanel";

export function ProjectSheet({
  opened,
  onClose,
}: {
  opened: boolean;
  onClose: () => void;
}) {
  return (
    <Drawer opened={opened} onClose={onClose} title="Projects" size={320}>
      <ProjectPanel />
    </Drawer>
  );
}
