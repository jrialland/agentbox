import { Button as MantineButton, type ButtonProps } from "@mantine/core";

export function Button({ variant = "filled", ...props }: ButtonProps) {
  return <MantineButton variant={variant} radius="sm" {...props} />;
}
