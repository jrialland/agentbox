import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { HelpProvider } from "../../help/HelpProvider";
import { ProviderForm } from "./ProviderForm";
import { EMPTY_PROVIDER_DRAFT, type ProviderDraft } from "./providerPresets";

const meta: Meta = { title: "Providers/Setup" };
export default meta;

function ProviderStory() {
  const [value, setValue] = useState<ProviderDraft>({
    ...EMPTY_PROVIDER_DRAFT,
    name: "DeepSeek",
    kind: "deepseek",
    baseUrl: "https://api.deepseek.com/v1",
    modelsUrl: "https://api.deepseek.com/v1/models",
  });
  return (
    <QueryClientProvider client={new QueryClient()}>
      <HelpProvider>
        <ProviderForm value={value} onChange={setValue} />
      </HelpProvider>
    </QueryClientProvider>
  );
}

export const Form: StoryObj = { render: () => <ProviderStory /> };
