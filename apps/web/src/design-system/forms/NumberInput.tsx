import {
  NumberInput as MantineNumberInput,
  type NumberInputProps,
} from "@mantine/core";

export function NumberInput(props: NumberInputProps) {
  return <MantineNumberInput radius="sm" {...props} />;
}
