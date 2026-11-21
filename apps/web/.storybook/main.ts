import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: [
    "../src/design-system/**/*.stories.@(ts|tsx)",
    "../src/chat/**/*.stories.@(ts|tsx)",
    "../src/help/**/*.stories.@(ts|tsx)",
    "../src/onboarding/**/*.stories.@(ts|tsx)",
    "../src/pages/**/*.stories.@(ts|tsx)",
  ],
  addons: ["@storybook/addon-docs", "@storybook/addon-a11y"],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
};

export default config;


