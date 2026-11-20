import "@mantine/core/styles.css";
import "@fontsource/silkscreen/400.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "../src/design-system/styles/layers.css";
import "../src/design-system/tokens/tokens.css";
import "../src/design-system/styles/global.css";

import type { Preview } from "@storybook/react-vite";

import { ThemeProvider } from "../src/design-system/theme/ThemeProvider";

const widths = {
  mobile: 390,
  tablet: 834,
  desktop: 1280,
} as const;

const preview: Preview = {
  parameters: {
    options: {
      storySort: {
        order: [
          "Foundations",
          "Icons",
          "Primitives",
          "Forms",
          "Data",
          "Overlays",
          "Navigation",
          "Patterns",
          "Shell",
        ],
      },
    },
    a11y: { test: "error" },
  },
  globalTypes: {
    theme: {
      name: "Theme",
      defaultValue: "dark",
      toolbar: {
        icon: "mirror",
        items: [
          { value: "dark", title: "Dark" },
          { value: "light", title: "Light" },
        ],
      },
    },
    viewport: {
      name: "Viewport",
      defaultValue: "desktop",
      toolbar: {
        icon: "mobile",
        items: [
          { value: "mobile", title: "Mobile 390" },
          { value: "tablet", title: "Tablet 834" },
          { value: "desktop", title: "Desktop 1280" },
        ],
      },
    },
  },
  decorators: [
    (Story, context) => {
      const theme = (context.globals.theme as "dark" | "light") ?? "dark";
      const viewport =
        (context.globals.viewport as keyof typeof widths) ?? "desktop";
      return (
        <ThemeProvider forceScheme={theme}>
          <div
            style={{
              width: widths[viewport],
              maxWidth: "100%",
              margin: "0 auto",
              padding: 24,
              background: "var(--ab-canvas)",
              color: "var(--ab-text)",
              minHeight: 240,
            }}
          >
            <Story />
          </div>
        </ThemeProvider>
      );
    },
  ],
};

export default preview;
