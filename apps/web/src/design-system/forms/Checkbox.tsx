import { Checkbox as MantineCheckbox, type CheckboxProps } from "@mantine/core";

export function Checkbox(props: CheckboxProps) {
  return <MantineCheckbox radius="sm" {...props} />;
}
