import { ActionIcon, Tooltip, type ActionIconProps } from "@mantine/core";
import type { RemixiconComponentType } from "@remixicon/react";

import { Icon } from "./Icon";

export function IconButton({
  label,
  icon,
  size = 18,
  tooltip = true,
  ...props
}: Omit<ActionIconProps, "aria-label"> & {
  label: string;
  icon: RemixiconComponentType;
  size?: 16 | 18 | 20 | 24;
  tooltip?: boolean;
}) {
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
