import { useComputedColorScheme } from "@mantine/core";
import { useEffect } from "react";

export function ThemeSync() {
  const scheme = useComputedColorScheme("light");
  useEffect(() => {
    document.documentElement.dataset.theme = scheme;
  }, [scheme]);
  return null;
}
