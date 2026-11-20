import type { RemixiconComponentType } from "@remixicon/react";

export function Icon({
  as: Component,
  size = 18,
  label,
  className,
}: {
  as: RemixiconComponentType;
  size?: 16 | 18 | 20 | 24;
  label?: string;
  className?: string;
}) {
  return (
    <Component
      className={className}
      size={size}
      aria-hidden={label ? undefined : "true"}
      role={label ? "img" : undefined}
      aria-label={label}
    />
  );
}
