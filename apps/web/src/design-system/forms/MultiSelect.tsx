import {
  MultiSelect as MantineMultiSelect,
  type MultiSelectProps,
} from "@mantine/core";

export function MultiSelect(props: MultiSelectProps) {
  return <MantineMultiSelect radius="sm" {...props} />;
}
