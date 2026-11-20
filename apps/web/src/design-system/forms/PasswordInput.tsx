import {
  PasswordInput as MantinePasswordInput,
  type PasswordInputProps,
} from "@mantine/core";

export function PasswordInput(props: PasswordInputProps) {
  return <MantinePasswordInput radius="sm" {...props} />;
}
