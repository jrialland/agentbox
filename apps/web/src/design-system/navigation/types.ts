import type { RemixiconComponentType } from "@remixicon/react";

export type NavItem = {
  to: string;
  label: string;
  icon: RemixiconComponentType;
  end?: boolean;
};
