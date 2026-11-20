import { Switch as MantineSwitch, type SwitchProps } from "@mantine/core";

export function Switch(props: SwitchProps) {
  return <MantineSwitch radius="sm" {...props} />;
}
