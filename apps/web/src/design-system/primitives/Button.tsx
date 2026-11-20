import { Button as MantineButton, type ButtonProps as MantineButtonProps } from "@mantine/core";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonProps = MantineButtonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "color"> & {
    children?: ReactNode;
  };

export function Button({ variant = "filled", ...props }: ButtonProps) {
  return <MantineButton variant={variant} radius="sm" {...props} />;
}
