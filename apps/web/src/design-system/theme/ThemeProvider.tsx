import {
  localStorageColorSchemeManager,
  MantineProvider,
  useComputedColorScheme,
} from "@mantine/core";
import { useEffect, type ReactNode } from "react";

import { theme } from "./theme";

const colorSchemeManager = localStorageColorSchemeManager({
  key: "agentbox-color-scheme",
});

function ThemeDomSync() {
  const scheme = useComputedColorScheme("dark");
  useEffect(() => {
    document.documentElement.dataset.theme = scheme;
  }, [scheme]);
  return null;
}

export function ThemeProvider({
  children,
  forceScheme,
}: {
  children: ReactNode;
  forceScheme?: "light" | "dark";
}) {
  return (
    <MantineProvider
      theme={theme}
      defaultColorScheme="auto"
      colorSchemeManager={colorSchemeManager}
      forceColorScheme={forceScheme}
    >
      <ThemeDomSync />
      {children}
    </MantineProvider>
  );
}
