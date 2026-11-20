import { Select as MantineSelect, type SelectProps } from "@mantine/core";

export function Select(props: SelectProps) {
  return <MantineSelect radius="sm" {...props} />;
}
