import { ActionIcon, Tooltip, type ActionIconProps } from "@mantine/core";
import type { RemixiconComponentType } from "@remixicon/react";
import type { ButtonHTMLAttributes } from "react";

import { Icon } from "./Icon";

type IconButtonProps = ActionIconProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "color" | "aria-label"> & {
    label: string;
    icon: RemixiconComponentType;
    size?: 16 | 18 | 20 | 24 | 32;
    tooltip?: boolean;
  };

export function IconButton({
  label,
  icon,
  size = 18,
  tooltip = true,
  ...props
}: IconButtonProps) {
  const button = (
    <ActionIcon aria-label={label} variant="subtle" color="gray" {...props}>
      <Icon as={icon} size={size} />
    </ActionIcon>
  );
  return tooltip ? (
    <Tooltip label={label} withArrow>
      {button}
    </Tooltip>
  ) : (
    button
  );
}
