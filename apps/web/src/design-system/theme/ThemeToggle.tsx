import {
  ActionIcon,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { RiMoonLine, RiSunLine } from "@remixicon/react";

export function ThemeToggle({ className }: { className?: string }) {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("dark");
  const next = scheme === "dark" ? "light" : "dark";
  const label = `Switch to ${next} theme`;

  return (
    <Tooltip label={label} withArrow>
      <ActionIcon
        className={className}
        variant="subtle"
        color="phosphor"
        aria-label={label}
        onClick={() => setColorScheme(next)}
      >
        {scheme === "dark" ? <RiSunLine size={18} /> : <RiMoonLine size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}
