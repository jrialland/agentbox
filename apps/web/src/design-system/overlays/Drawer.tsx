import { Drawer as MantineDrawer, type DrawerProps } from "@mantine/core";

export function Drawer(props: DrawerProps) {
  return <MantineDrawer radius="md" position="right" {...props} />;
}
